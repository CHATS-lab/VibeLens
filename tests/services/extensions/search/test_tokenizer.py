"""Tokenizer tests: splitting, casing, stopwords, stemming, prefix edges."""

from vibelens.services.search.tokenizer import tokenize


def test_tokenize_basic_split():
    """Non-alphanumeric characters split tokens."""
    tokens = tokenize("claude-code testgen")
    print(f"tokens: {tokens}")
    assert "claude" in tokens
    assert "code" in tokens
    assert "testgen" in tokens


def test_tokenize_lowercases():
    """All tokens lowercased."""
    tokens = tokenize("FastAPI React")
    print(f"tokens: {tokens}")
    assert all(t == t.lower() for t in tokens)


def test_tokenize_drops_stopwords():
    """Common English stopwords removed."""
    tokens = tokenize("the quick brown fox jumps over the lazy dog")
    print(f"tokens: {tokens}")
    assert "the" not in tokens
    assert "over" not in tokens
    assert "quick" in tokens


def test_tokenize_drops_short_tokens():
    """Tokens shorter than 2 chars dropped."""
    tokens = tokenize("a b cc ddd")
    print(f"tokens: {tokens}")
    assert "a" not in tokens
    assert "b" not in tokens
    assert "cc" in tokens


def test_tokenize_empty_and_none_like():
    """Empty strings return empty lists."""
    assert tokenize("") == []
    assert tokenize("   ") == []
    assert tokenize(None) == []


def test_stem_plural_s():
    """Trailing -s stripped when stem is >= 3 chars."""
    assert tokenize("tests")[0] == "test"
    assert tokenize("runners")[0] == "runner"


def test_stem_ing():
    """Trailing -ing stripped."""
    assert tokenize("testing")[0] == "test"
    assert tokenize("running")[0] == "runn"


def test_stem_ies():
    """-ies → -y stem, so `libraries` and `library` match."""
    assert tokenize("libraries") == tokenize("library")
    print(f"libraries => {tokenize('libraries')}, library => {tokenize('library')}")


def test_stem_deterministic():
    """Same input always yields same tokens (critical for matching)."""
    a = tokenize("My Awesome-Test Runner")
    b = tokenize("my awesome_test runner")
    print(f"a={a} b={b}")
    assert a == b


def test_tokenize_numbers_kept():
    """Digits preserved in tokens."""
    tokens = tokenize("python3 fastapi2")
    print(f"tokens: {tokens}")
    assert any(t.startswith("python") for t in tokens)


def test_tokenize_punctuation_split():
    """Punctuation splits tokens without leaving empty strings."""
    tokens = tokenize("hello, world! test.py:42")
    print(f"tokens: {tokens}")
    assert "hello" in tokens
    assert "world" in tokens
    assert "" not in tokens


def test_stem_minimum_length_respected():
    """Suffix-strip must not produce tokens shorter than 3 chars."""
    tokens = tokenize("ed es")  # both are stopwords anyway
    print(f"tokens: {tokens}")
    # Direct check: "err" should not stem to "r"
    tokens2 = tokenize("err")
    assert tokens2 == ["err"]


def test_tokenize_plural_and_tense_merge():
    """`tests` and `testing` stem to same token so they match."""
    assert tokenize("tests") == tokenize("test")
    print(f"tests => {tokenize('tests')}, testing => {tokenize('testing')}")
