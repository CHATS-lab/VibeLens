"""Quality tests over a 20-session synthetic catalog.

Exercises the scorer + tokenizer + AND semantics end-to-end. The
catalog is small but realistic: mixed content types, shared topics,
natural English sentences — so BM25 IDF produces meaningful deltas.
"""

from tests.services.session.search._fixtures import (
    build_index_from_entries,
    make_synthetic_entry,
)


def _realistic_catalog():
    """20 synthetic sessions spanning several topics."""
    rows = [
        ("s01-auth-jwt",
         "how do I verify jwt tokens in a fastapi middleware",
         "check the iss and exp claims; use python-jose"),
        ("s02-react-state",
         "react useState hook for form inputs",
         "useState returns a pair, state and setter"),
        ("s03-pytest-fix",
         "pytest fixture scope question",
         "scope=module shares across tests in one file"),
        ("s04-rust-async",
         "rust tokio async runtime panic",
         "use tokio spawn and await the join handle"),
        ("s05-sql-index",
         "sql postgres index optimization slow query",
         "explain analyze shows seq scan; add btree index"),
        ("s06-docker-build",
         "docker multi-stage build cache hit",
         "use BuildKit cache mounts to reuse layers"),
        ("s07-css-grid",
         "css grid vs flexbox for dashboard",
         "grid for 2D layouts, flexbox for 1D rows"),
        ("s08-vue-compose",
         "vue 3 composition api reactive question",
         "reactive() for objects, ref() for primitives"),
        ("s09-go-chan",
         "golang channel deadlock debugging",
         "use select with default to avoid blocking"),
        ("s10-ml-train",
         "pytorch model training loss plateau",
         "reduce learning rate or try weight decay"),
        ("s11-next-deploy",
         "nextjs 14 vercel deployment error",
         "check the edge runtime limits and env vars"),
        ("s12-k8s-helm",
         "kubernetes helm chart templating values",
         "use values.yaml for environment overrides"),
        ("s13-git-rebase",
         "git interactive rebase squash commits",
         "rebase -i lets you squash and reorder"),
        ("s14-django-orm",
         "django queryset prefetch_related vs select_related",
         "select_related for foreign keys, prefetch for many"),
        ("s15-aws-lambda",
         "aws lambda cold start optimization python",
         "use provisioned concurrency or lighter deps"),
        ("s16-graphql-n1",
         "graphql n+1 query problem with dataloader",
         "batch requests with dataloader per request"),
        ("s17-node-stream",
         "nodejs stream backpressure pipe",
         "use pipeline from stream/promises"),
        ("s18-swift-ui",
         "swiftui state binding observable",
         "use @ObservedObject or @StateObject as appropriate"),
        ("s19-mongo-agg",
         "mongodb aggregation pipeline group by",
         "use $group with $sum accumulator"),
        ("s20-scala-fp",
         "scala functional programming for comprehensions",
         "yield keyword desugars to flatMap and map"),
    ]
    entries = []
    for i, (sid, user_text, agent_text) in enumerate(rows):
        entries.append(
            make_synthetic_entry(
                sid,
                user_text=user_text,
                agent_text=agent_text,
                offset_days=i,
            )
        )
    return entries


def test_exact_sid_always_ranks_first():
    """Every session should rank #1 when queried by its own exact sid."""
    entries = _realistic_catalog()
    idx = build_index_from_entries(entries)
    misses = []
    for e in entries:
        out = idx.search_full(e.session_id)
        top = out[0][0] if out else ""
        if top != e.session_id:
            misses.append(f"{e.session_id} -> got {top}")
    print(f"{len(misses)}/{len(entries)} exact-sid misses")
    for m in misses[:5]:
        print(f"  - {m}")
    assert misses == []


def test_prefix_sid_finds_target_in_top_three():
    """Typing the first sid segment finds the right session in top 3."""
    entries = _realistic_catalog()
    idx = build_index_from_entries(entries)
    # The catalog's sid first segments are unique (s01..s20), so each
    # first segment matches exactly one session.
    for e in entries:
        prefix = e.session_id.split("-")[0]
        out = idx.search_full(prefix)
        top3 = [sid for sid, _ in out[:3]]
        print(f"{prefix} -> {top3}")
        assert e.session_id in top3, f"{e.session_id} missing for prefix {prefix}"


def test_content_query_top_five_pass_rate():
    """At least 90% of natural-language queries find the target in top 5."""
    entries = _realistic_catalog()
    idx = build_index_from_entries(entries)
    queries = [
        ("jwt fastapi", "s01-auth-jwt"),
        ("react useState", "s02-react-state"),
        ("pytest fixture scope", "s03-pytest-fix"),
        ("rust tokio", "s04-rust-async"),
        ("postgres index", "s05-sql-index"),
        ("docker cache", "s06-docker-build"),
        ("css grid layout", "s07-css-grid"),
        ("vue composition", "s08-vue-compose"),
        ("go channel deadlock", "s09-go-chan"),
        ("pytorch training", "s10-ml-train"),
        ("nextjs deploy", "s11-next-deploy"),
        ("helm chart", "s12-k8s-helm"),
        ("git squash", "s13-git-rebase"),
        ("prefetch_related", "s14-django-orm"),
        ("lambda cold start", "s15-aws-lambda"),
        ("dataloader n+1", "s16-graphql-n1"),
        ("stream pipeline", "s17-node-stream"),
        ("swiftui observable", "s18-swift-ui"),
        ("mongodb aggregation", "s19-mongo-agg"),
        ("scala flatMap", "s20-scala-fp"),
    ]
    hits = 0
    for q, expected in queries:
        out = idx.search_full(q)
        top5 = [sid for sid, _ in out[:5]]
        ok = expected in top5
        print(f"{'OK ' if ok else '-- '} {q:30s} -> {top5[:3]} (want {expected})")
        if ok:
            hits += 1
    print(f"top-5 pass: {hits}/{len(queries)}")
    assert hits >= int(len(queries) * 0.9)


def test_nonsense_query_returns_empty():
    """A query that matches nothing returns an empty list."""
    entries = _realistic_catalog()
    idx = build_index_from_entries(entries)
    assert idx.search_full("zqx999nothing") == []


def test_empty_query_returns_none_from_full():
    """Empty query returns None from search_full so the caller can fall back."""
    entries = _realistic_catalog()
    idx = build_index_from_entries(entries)
    assert idx.search_full("") is None
