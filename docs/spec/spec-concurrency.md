# Concurrency

How VibeLens handles shared mutable state in a single-process server.

## Motivation

VibeLens runs as a single-process, single-worker uvicorn server. The simplest possible deployment — but it serves multiple users in demo mode, multiple browser tabs in self-mode, and routinely dispatches blocking work onto a shared thread pool. That gives three classes of contention to think about:

- **Files on disk** — JSONL appends and rewrites that two requests can race on.
- **In-memory caches and registries** — module-level dicts that can be read on the event loop while a thread is mid-update.
- **DI singletons / config** — lazy-built objects accessed from many code paths.

This spec lays out the execution model and the invariants every shared resource is required to maintain. Specific bug-tracker entries don't belong here; the rules below do.

## Execution model

```
                    uvicorn (1 worker, 1 process)
                               │
                       asyncio event loop
                      ╱        │        ╲
              coroutine A  coroutine B  coroutine C
                   │           │
              to_thread()  to_thread()
                   │           │
            shared thread pool (default ≈ 40 threads)
```

Everything is in one process, one event loop. `asyncio.to_thread()` dispatches blocking work into a shared thread pool. All coroutines and threads share the same dictionaries, file handles, and singletons.

What this means in practice:

- Synchronous code between two `await` points runs without interleaving — pure-async dict operations don't race against each other.
- Code inside `to_thread()` *does* run concurrently with the event loop and with other thread-pool work — those are real races.
- Multi-process scaling (multiple uvicorn workers) is not a goal; if it becomes one, every in-memory cache becomes per-process and would need an external store.

## Invariants by resource type

### Append-only JSONL files

Every JSONL the server writes (`metadata.jsonl`, donation index, friction store, skill store, share registry) is appended through `utils/json.locked_jsonl_append`, which holds `fcntl.flock(LOCK_EX)` across the write+flush. Two concurrent appends serialise; lines never interleave.

Reads use `_iter_jsonl`, which skips malformed lines silently — a corrupt append would otherwise drop a session, so the lock is the only safe contract.

### Read-modify-write on JSONL

Delete-style operations (`locked_jsonl_remove`) hold the same exclusive lock across the whole read → filter → rewrite cycle. A concurrent append must not slip in between read and write.

### Files written atomically

Anything written as a whole document — config files (`config/llm.yaml`), the session index cache (`session_index.json`), the share registry, per-upload `result.json` — uses `utils/json.atomic_write_json` (write to temp + rename). Concurrent readers always see either the old or the new file, never a half-written one.

### In-memory caches

Module-level cache dicts (dashboard TTL caches, tool-usage cache, store registries, parser-instance cache) follow one rule: **mutations happen on the event loop, not in `to_thread()`**. When a heavy build must run in a thread (e.g. a fast-path aggregation), it returns a fresh dict and the event loop swaps it in atomically. Threads never mutate live cache dicts in place.

Where a build inherently needs to mutate shared state from a thread, the resource carries a `threading.Lock` and the read path acquires it before iterating.

### DI singletons and registries

`deps.py` holds the lazy-built singletons (LLM client, store registry, share service). Construction is guarded by a `threading.Lock` so two coroutines that both call `to_thread()` and both miss the cache don't both build. After construction the singleton is read-only — the lock isn't held on the read path.

Per-token store registration (the `(session_token, upload_id)` map in the upload pipeline) is an event-loop-only structure; it's mutated from the request handler before any `to_thread()` returns.

## Threat model

| Vector | Why it matters |
|---|---|
| Concurrent uploads | Every upload appends to `metadata.jsonl` and registers a store. Lock contention is real but bounded; thread-pool saturation is the bigger risk on large zips. |
| Upload + dashboard read | Cache invalidation runs on the event loop; the dashboard request is async-only on the cache-hit path. The race is only on the rebuild path. |
| Concurrent LLM analyses | Each analysis queues batches of LLM calls; the batcher is stateless, but the friction/skill stores receive concurrent appends — covered by JSONL lock. |
| Concurrent donations | Donation history JSONL append (lock-covered); the sender holds no shared state. |
| Background warmup vs. foreground requests | Cache warmup runs as a `to_thread()` task; the event loop swaps the result in atomically. A foreground request that arrives mid-warmup falls through to the synchronous build, which is correct (just slower). |

## Performance profile

What the single-worker model can absorb before backpressure shows up:

- **Async-only endpoints** (dashboard cache hits, search query, list metadata) — bounded by event-loop cost. Hundreds of req/s is comfortable.
- **Thread-pool endpoints** (upload, donation send, LLM analysis dispatch) — bounded by the thread pool. Default 40 threads handles ~20 concurrent active users with real headroom.
- **JSONL lock contention** — single-digit ms per append; serialises one append at a time per file.

Scaling levers, in increasing cost:

1. Increase the asyncio thread pool size if uploads dominate.
2. Add a `Semaphore` per endpoint group (upload, LLM, donation) to give backpressure earlier than the thread-pool exhaustion edge.
3. Move to multiple uvicorn workers — at which point in-memory caches become per-process and would need either to be rebuilt per-worker or persisted (TTL caches are cheap to rebuild; the upload registry already replays from `metadata.jsonl`).

## Out of scope

- Cross-process locks. The single-process assumption is load-bearing; if this changes, every "module-level dict" invariant in this spec needs revisiting.
- Distributed coordination (Redis, etc.). VibeLens stays single-host; the donation server is a separate service with its own concurrency story.
