# Concurrency

Concurrency audit and hardening plan for multi-user deployment. Catalogs race conditions in the single-process uvicorn server and tracks fixes.

## Purpose

VibeLens runs as a single-process, single-worker uvicorn server using `asyncio.to_thread()` for blocking I/O. This works fine for single-user local use, but multi-user deployment (demo mode) exposes race conditions on shared mutable resources: JSONL files, in-memory caches, and DI singletons. This spec catalogs every hazard and tracks resolution.

## Execution Model

```
                    uvicorn (1 worker, 1 process)
                               |
                      asyncio event loop
                     /         |         \
               coroutine A  coroutine B  coroutine C
                    |          |            |
              to_thread()  to_thread()   (async I/O)
                    |          |
             Thread Pool (default: 40 threads)
```

All coroutines share process memory. `to_thread()` dispatches blocking work to a shared thread pool. Module-level dicts and file handles are accessible from every thread and coroutine simultaneously.

## Threat Model

| Vector | Frequency |
|--------|-----------|
| Concurrent uploads | High |
| Upload + dashboard read (cache invalidation) | High |
| Concurrent LLM analyses | Medium |
| Concurrent donations | Medium |
| Concurrent config writes | Low |
| Background warmup vs. foreground requests | Every startup |

## Issue Tracker

### P0 -- Data Corruption

- [x] **JSONL append locking** -- `locked_jsonl_append()` in `utils/json.py` with `fcntl.flock()`. Applied to: DiskStore index, upload metadata, donation index, friction store, skill store.

### P0.5 -- Event Loop Performance

- [x] **Offload blocking calls** -- `locked_jsonl_append()` and `cleanup_extraction()` wrapped in `asyncio.to_thread()`.

### P1 -- Silent Data Loss

- [ ] **Non-atomic multi-step writes** -- `DiskStore.save()` and `ShareService.create_share()` need temp + rename pattern.
- [x] **JSONL read-modify-write locking** -- `locked_jsonl_remove()` in `utils/json.py` for delete operations in friction and skill stores.
- [ ] **Storage layer index cache locks** -- DiskStore needs `threading.RLock`; LocalStore needs wider `_build_lock` scope.

### P2 -- State Inconsistency

- [ ] **DI singleton registry lock** -- `threading.Lock` in `deps.py` for `_get_or_create()` and `set_llm_config()`.
- [ ] **LLM config atomic write** -- temp + rename for `config/llm.yaml`.
- [ ] **API concurrency control** -- `asyncio.Semaphore` per endpoint group (uploads: 3-5, LLM: 2, donation: 3, config: 1).

### P3 -- Defensive Hardening

- [ ] **Upload ID entropy** -- increase from 4 to 8 hex chars (collision risk at scale).
- [ ] **Background warmup sync** -- `asyncio.Event` gate so first request waits for cache warming.
- [ ] **Persistent index cache atomic write** -- temp + rename for `index_cache.json`.
- [ ] **In-memory cache locks** -- `threading.Lock` per cache dict (needed when `to_thread()` causes real thread concurrency).

## Key Race Conditions

### JSONL Append (Fixed)

Without file locking, concurrent `open("index.jsonl", "a")` + `write()` from two threads can interleave bytes, producing corrupt JSON lines. `_iter_jsonl()` silently skips corrupt lines, causing sessions to vanish.

**Fix:** `locked_jsonl_append()` acquires `fcntl.flock(LOCK_EX)` before write, releases after flush.

### JSONL Read-Modify-Write (Fixed)

Delete operations read JSONL, filter, and rewrite. A concurrent append between read and write is lost.

**Fix:** `locked_jsonl_remove()` holds exclusive lock for entire read-filter-write cycle.

### Storage Index Cache

`DiskStore` has no locking. `invalidate_index()` can set `_metadata_cache = None` while another thread is mid-update, causing writes to a discarded dict.

### In-Memory Caches

Six module-level cache dicts are unprotected. In single-worker asyncio, coroutines don't interleave between `await` points, so synchronous dict ops are safe. The real race is `warm_cache()` running in a thread (via `to_thread()`) while the event loop reads the same dict.

## Performance Profile

### Concurrent Uploads (10 Users)

| Phase | Duration | Blocks Event Loop? |
|-------|----------|-------------------|
| Stream ZIP to disk | 50-100ms | No (async) |
| Extract + discover | 15-30ms | No (thread pool) |
| Parse + anonymize + store | 110-140ms | No (thread pool) |
| Metadata append (locked) | 5-10ms | Yes |
| Cache invalidation | < 1ms | Yes (trivial) |
| Cleanup extracted dir | 20-50ms | Yes |

Thread pool usage: 10 uploads use 10 of 40 threads. No saturation. Lock serialization at metadata append: 50-100ms total for all 10 uploads. Memory: ~100-150MB (10 x 15MB per upload).

### Single Worker Sufficient For

- < 20 concurrent users (typical demo load)
- Dashboard/search endpoints are pure async (no thread consumption)
- Uploads dispatch heavy work to thread pool

### Scaling Options

| Option | Impact | Effort |
|--------|--------|--------|
| Offload blocking calls to thread pool | High | Small |
| Semaphore cap on concurrent uploads | High | Small |
| Increase thread pool size | Medium | One-line |
| Multiple uvicorn workers | Medium | Config (caches become per-process) |
