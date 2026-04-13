"""Parse YAML frontmatter from Markdown files."""

import yaml


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a Markdown string.

    Args:
        text: Full file content with optional ``---`` delimited YAML block.

    Returns:
        Tuple of (metadata_dict, body_string). metadata_dict is empty if
        no frontmatter is found.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text

    # Find closing ---
    end_idx = stripped.find("---", 3)
    if end_idx == -1:
        return {}, text

    yaml_block = stripped[3:end_idx]
    body = stripped[end_idx + 3:].lstrip("\n")

    try:
        meta = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        # Fall back to line-by-line parsing for files with non-standard YAML
        # (e.g., Claude command files with `argument-hint: [val] | --flag`).
        meta = _parse_frontmatter_lines(yaml_block)

    if not isinstance(meta, dict):
        return {}, text

    return meta, body


def _parse_frontmatter_lines(yaml_block: str) -> dict:
    """Parse a YAML block line by line, skipping unparseable lines.

    Used as a fallback when ``yaml.safe_load`` fails on non-standard syntax.

    Args:
        yaml_block: Raw text between the ``---`` delimiters.

    Returns:
        Dict of successfully parsed key-value pairs (skips malformed lines).
    """
    result: dict = {}
    for line in yaml_block.splitlines():
        stripped_line = line.strip()
        if not stripped_line or ":" not in stripped_line:
            continue
        try:
            parsed = yaml.safe_load(stripped_line)
            if isinstance(parsed, dict):
                result.update(parsed)
        except yaml.YAMLError:
            # Skip lines that cannot be parsed individually
            pass
    return result


def extract_tags(meta: dict) -> list[str]:
    """Extract tags from frontmatter metadata.

    Pulls category and keywords/tags fields, deduplicates preserving order.

    Args:
        meta: Parsed frontmatter metadata dict.

    Returns:
        Deduplicated list of tag strings.
    """
    tags: list[str] = []
    if "category" in meta:
        tags.append(meta["category"])
    keywords = meta.get("keywords") or meta.get("tags") or []
    if isinstance(keywords, list):
        tags.extend(str(k) for k in keywords)
    elif isinstance(keywords, str):
        tags.extend(k.strip() for k in keywords.split(","))
    return list(dict.fromkeys(tags))  # dedupe preserving order
