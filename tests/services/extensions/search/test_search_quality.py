"""Quality tests over a realistic-scale synthetic catalog.

Exercises rank_catalog end-to-end against a catalog large enough for
BM25 IDF to behave normally (~50 items). Keeps the test fast (<1s)
while catching regressions in tokenization, field weighting, and
the combined scoring path.
"""

from tests.services.extensions.search._fixtures import make_item
from vibelens.services.extensions.search.index import CatalogSearchIndex
from vibelens.services.extensions.search.query import SortMode
from vibelens.services.extensions.search.scorer import rank_extensions


def _realistic_catalog() -> list:
    """Build a ~50-item synthetic catalog across several domains."""
    rows = [
        ("pytest-runner", "Run pytest with retries and rich output", ["python", "testing"]),
        ("skill-tdd", "Test-driven development helper for Python", ["python", "testing"]),
        ("testgen", "Generate test scaffolding", ["testing"]),
        ("fastapi-starter", "FastAPI project scaffold", ["python", "fastapi"]),
        ("react-helper", "React component patterns", ["react", "frontend"]),
        ("next-starter", "Next.js app scaffold", ["react", "frontend"]),
        ("vue-helper", "Vue.js component helpers", ["vue", "frontend"]),
        ("svelte-helper", "Svelte component patterns", ["svelte", "frontend"]),
        ("code-review", "Review code against standards", ["review"]),
        ("security-scan", "Scan for OWASP vulnerabilities", ["security"]),
        ("sql-helper", "SQL query formatting and lint", ["sql", "database"]),
        ("postgres-mcp", "Postgres MCP server integration", ["postgres", "mcp"]),
        ("docker-helper", "Dockerfile generation", ["docker"]),
        ("k8s-helper", "Kubernetes manifest templates", ["kubernetes"]),
        ("git-helper", "Git workflow automation", ["git"]),
        ("go-helper", "Go language patterns", ["go"]),
        ("rust-helper", "Rust systems programming", ["rust"]),
        ("ml-helper", "Machine learning experiment tracking", ["ml"]),
        ("data-pipeline", "ETL pipeline scaffolding", ["data"]),
        ("api-gateway", "API gateway configuration", ["api"]),
        ("bash-scripts", "Shell script helpers", ["bash"]),
        ("json-schema", "JSON schema validation", ["json"]),
        ("yaml-helper", "YAML configuration manager", ["yaml"]),
        ("markdown-fmt", "Markdown formatter", ["markdown"]),
        ("image-helper", "Image processing pipeline", ["image"]),
        ("video-helper", "Video editing helpers", ["video"]),
        ("audio-helper", "Audio processing helpers", ["audio"]),
        ("pdf-helper", "PDF generation and parsing", ["pdf"]),
        ("csv-helper", "CSV reader and writer", ["csv"]),
        ("api-helper", "REST API client patterns", ["api"]),
        ("graphql-helper", "GraphQL query builder", ["graphql"]),
        ("websocket-helper", "WebSocket connection manager", ["websocket"]),
        ("cache-helper", "Redis caching patterns", ["redis", "cache"]),
        ("queue-helper", "Message queue integration", ["queue"]),
        ("notification-helper", "Push notification service", ["notification"]),
        ("email-helper", "Email template builder", ["email"]),
        ("auth-helper", "Authentication patterns", ["auth"]),
        ("oauth-helper", "OAuth2 client library", ["oauth"]),
        ("jwt-helper", "JWT token management", ["jwt"]),
        ("session-helper", "Session management", ["session"]),
        ("cookie-helper", "Cookie handling", ["cookie"]),
        ("form-helper", "Form validation patterns", ["form"]),
        ("chart-helper", "Charting library wrapper", ["chart"]),
        ("date-helper", "Date parsing and formatting", ["date"]),
        ("time-helper", "Time zone conversion", ["time"]),
        ("string-helper", "String manipulation utilities", ["string"]),
        ("regex-helper", "Regular expression builder", ["regex"]),
        ("log-helper", "Structured logging helpers", ["logging"]),
        ("metrics-helper", "Prometheus metrics", ["metrics"]),
        ("trace-helper", "Distributed tracing", ["tracing"]),
    ]
    return [make_item(name, description=desc, topics=topics) for name, desc, topics in rows]


def test_self_match_on_name_ranks_first():
    """Every item should rank #1 when queried by its own name."""
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    mismatches: list[str] = []
    for item in items:
        ranked = rank_extensions(idx, item.name, [], SortMode.DEFAULT)
        top_id = ranked[0].extension_id if ranked else ""
        if top_id != item.extension_id:
            mismatches.append(f"{item.name}: expected {item.extension_id}, got {top_id}")
    print(f"{len(mismatches)}/{len(items)} self-match failures")
    for m in mismatches[:5]:
        print(f"  - {m}")
    # Allow up to 10% mismatch for names like "helper" that collide across items.
    assert len(mismatches) <= len(items) // 10


def test_python_testing_finds_testing_items():
    """A 'python testing' query ranks pytest/tdd items in the top 5."""
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "python testing", [], SortMode.DEFAULT)
    top5 = [r.extension_id.split("/")[-1] for r in ranked[:5]]
    print(f"python testing top5: {top5}")
    testing_items = {"pytest-runner", "skill-tdd", "testgen"}
    hits = testing_items & set(top5)
    assert len(hits) >= 2


def test_frontend_query_finds_frontend_items():
    """A 'react component' query ranks react/frontend items in the top 5."""
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "react component", [], SortMode.DEFAULT)
    top5 = [r.extension_id.split("/")[-1] for r in ranked[:5]]
    print(f"react component top5: {top5}")
    assert "react-helper" in top5


def test_prefix_match_on_partial_token():
    """User typing 'testg' (partial) still surfaces 'testgen'."""
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "testg", [], SortMode.DEFAULT)
    top3 = [r.extension_id.split("/")[-1] for r in ranked[:3]]
    print(f"'testg' prefix top3: {top3}")
    assert "testgen" in top3


def test_nonsense_query_returns_empty():
    """A made-up query matches nothing and returns an empty list."""
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "xyzqqqq", [], SortMode.DEFAULT)
    print(f"nonsense results: {len(ranked)}")
    assert ranked == []


def test_multi_token_query_requires_all_tokens():
    """A two-token query returns only items matching BOTH tokens (AND).

    Regression for a bug where BM25's OR-like scoring caused unrelated
    items to rank high because they matched one of the query terms.
    """
    items = _realistic_catalog()
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "python testing", [], SortMode.DEFAULT)
    # Items below have positive text scores (passed through the filter).
    matching = [r for r in ranked if r.signal_breakdown.get("text", 0.0) > 0.0]
    names = [r.extension_id.split("/")[-1] for r in matching]
    print(f"'python testing' AND matches: {names}")
    # Must contain items mentioning both python AND testing.
    assert "pytest-runner" in names
    assert "skill-tdd" in names
    # Must NOT contain python-only (fastapi-starter mentions python but not testing).
    assert "fastapi-starter" not in names
    # Must NOT contain testing-only (testgen mentions testing but not python).
    assert "testgen" not in names
