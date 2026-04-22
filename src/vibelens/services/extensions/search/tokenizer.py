"""Catalog search tokenizer.

Pure functions, no state. Consumers pass strings in, get token lists out.
Same tokenizer used at index build and at query time.
"""

import re

# Match one run of alphanumeric chars. Exposed for code that needs to split
# text on the same boundaries as ``tokenize`` but without stopword/stem logic
# (e.g. raw-name token extraction for exact-match tiering).
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN = 2
_MIN_STEM_LEN = 3

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "for", "nor", "so", "yet",
    "to", "of", "in", "on", "at", "by", "from", "up", "as", "with",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "doing", "done",
    "have", "has", "had", "having",
    "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "us", "our", "ours",
    "you", "your", "yours", "yourself",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs",
    "what", "which", "who", "whom", "whose",
    "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "not", "only", "own", "same",
    "than", "then", "there", "through", "too", "very",
    "can", "will", "just", "should", "would", "could", "may", "might",
    "must", "shall", "ought",
    "if", "else", "while", "until", "because", "since",
    "about", "above", "across", "after", "against", "along", "among",
    "around", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "during", "except", "inside", "into", "like", "near",
    "off", "onto", "out", "outside", "over", "past", "throughout",
    "under", "underneath", "unlike", "upon", "within", "without",
    "again", "further", "once", "also",
    "s", "t", "d",
    "get", "got", "go", "goes", "going", "gone",
    "make", "made", "making", "way", "ways",
    "via", "use", "used", "using", "new", "old",
})


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, drop short/stop, stem.

    Args:
        text: Arbitrary input text; tolerates None-like empties.

    Returns:
        List of tokens, each length >= 2. Stable and deterministic.
    """
    if not text:
        return []
    tokens = _TOKEN_RE.findall(text.lower())
    return [
        _stem(t) for t in tokens if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS
    ]


def _stem(token: str) -> str:
    """Strip common English inflectional suffixes.

    Deliberately conservative: we only merge forms that are almost always
    the same concept in this domain (tests/testing/tested) and refuse
    rules that collapse unrelated words (paper/paper-er, postgres/postgr-es).
    Specifically, we do NOT strip `-er` or `-es` because English nouns
    that end that way are rarely verb derivations — "paper" is not
    "pap+er", "postgres" is not "postgr+es".
    """
    if token.endswith("ies") and len(token) - 3 >= _MIN_STEM_LEN:
        return f"{token[:-3]}y"
    for suffix in ("ing", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= _MIN_STEM_LEN:
            return token[: -len(suffix)]
    return token
