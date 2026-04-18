"""Build VibeLens's bundled catalog from agent-tool-hub output.

Reads the six ``agent-<type>.json`` files emitted by agent-tool-hub, copies
them byte-for-byte into ``src/vibelens/data/catalog/``, computes a summary
projection plus a byte-offset index, and writes a manifest.

Run from the repo root::

    uv run python scripts/build_catalog.py \\
        --hub-output /path/to/agent-tool-hub/output/full-YYYYMMDD-HHMMSS \\
        --out src/vibelens/data/catalog
"""

import argparse
import json
import math
import random
import shutil
import sys
import tempfile
from pathlib import Path

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.storage.extension.json_item_scanner import scan_items

HUB_TYPES: tuple[AgentExtensionType, ...] = (
    AgentExtensionType.SKILL,
    AgentExtensionType.PLUGIN,
    AgentExtensionType.SUBAGENT,
    AgentExtensionType.COMMAND,
    AgentExtensionType.HOOK,
    AgentExtensionType.MCP_SERVER,
)

SUMMARY_OMITTED_FIELDS: frozenset[str] = frozenset(
    {
        "repo_description",
        "readme_description",
        "author",
        "scores",
        "item_metadata",
        "validation_errors",
        "author_followers",
        "contributors_count",
        "created_at",
        "discovery_origin",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hub-output", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    generated_on = _validate_hub_dir(args.hub_output)
    hub_source = args.hub_output.name

    with tempfile.TemporaryDirectory() as scratch:
        scratch_dir = Path(scratch)
        _copy_hub_files(src=args.hub_output, dst=scratch_dir)
        offsets, summaries, item_counts, file_sizes = _scan_all(scratch_dir)
        _fill_derived(summaries)
        _write_summary(scratch_dir, generated_on=generated_on, summaries=summaries)
        _write_offsets(scratch_dir, offsets=offsets)
        _write_manifest(
            scratch_dir,
            generated_on=generated_on,
            hub_source=hub_source,
            total=len(summaries),
            item_counts=item_counts,
            file_sizes=file_sizes,
        )
        _sanity_check(scratch_dir, offsets=offsets)
        _atomic_replace(src=scratch_dir, dst=args.out)

    print(f"wrote catalog to {args.out} ({len(summaries)} items, hub={hub_source})")
    return 0


def _validate_hub_dir(hub_dir: Path) -> str:
    if not hub_dir.is_dir():
        sys.exit(f"hub output not a directory: {hub_dir}")
    seen: set[str] = set()
    for t in HUB_TYPES:
        path = hub_dir / f"agent-{t.value}.json"
        if not path.is_file():
            sys.exit(f"missing hub file: {path}")
        with path.open("rb") as f:
            head = f.read(512).decode("utf-8", errors="replace")
        date = _extract_generated_on(head)
        if date is None:
            sys.exit(f"no generated_on in {path}")
        seen.add(date)
    if len(seen) > 1:
        sys.exit(f"hub files have mismatched generated_on values: {sorted(seen)}")
    return seen.pop()


def _extract_generated_on(head: str) -> str | None:
    needle = '"generated_on"'
    start = head.find(needle)
    if start < 0:
        return None
    colon = head.find(":", start)
    quote = head.find('"', colon)
    end = head.find('"', quote + 1)
    if colon < 0 or quote < 0 or end < 0:
        return None
    return head[quote + 1 : end]


def _copy_hub_files(src: Path, dst: Path) -> None:
    for t in HUB_TYPES:
        shutil.copyfile(src / f"agent-{t.value}.json", dst / f"agent-{t.value}.json")


def _scan_all(
    dst: Path,
) -> tuple[
    dict[str, tuple[str, int, int]],
    list[dict],
    dict[str, int],
    dict[str, int],
]:
    offsets: dict[str, tuple[str, int, int]] = {}
    summaries: list[dict] = []
    item_counts: dict[str, int] = {}
    file_sizes: dict[str, int] = {}

    for t in HUB_TYPES:
        path = dst / f"agent-{t.value}.json"
        buf = path.read_bytes()
        file_sizes[path.name] = len(buf)
        type_count = 0
        for extension_id, offset, length in scan_items(buf, id_key="item_id"):
            offsets[extension_id] = (t.value, offset, length)
            item_bytes = buf[offset : offset + length]
            summary = _project_summary(item_bytes)
            summaries.append(summary)
            type_count += 1
        item_counts[t.value] = type_count

    return offsets, summaries, item_counts, file_sizes


def _project_summary(item_bytes: bytes) -> dict:
    """Parse an item and drop detail-only fields."""
    item = AgentExtensionItem.model_validate_json(item_bytes)
    dumped = item.model_dump(mode="json", by_alias=False)
    for field in SUMMARY_OMITTED_FIELDS:
        dumped.pop(field, None)
    dumped["platforms"] = None
    dumped["install_command"] = None
    dumped["popularity"] = 0.0
    return dumped


def _fill_derived(summaries: list[dict]) -> None:
    """Fill popularity = log1p(stars) / log1p(MAX_STARS)."""
    max_stars = max((s.get("stars") or 0 for s in summaries), default=0)
    denom = math.log1p(max_stars) if max_stars > 0 else 1.0
    for s in summaries:
        stars = s.get("stars") or 0
        s["popularity"] = math.log1p(stars) / denom if denom else 0.0


def _write_summary(dst: Path, generated_on: str, summaries: list[dict]) -> None:
    payload = {"generated_on": generated_on, "total": len(summaries), "items": summaries}
    (dst / "catalog-summary.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_offsets(dst: Path, offsets: dict[str, tuple[str, int, int]]) -> None:
    serializable = {k: list(v) for k, v in offsets.items()}
    (dst / "catalog-offsets.json").write_text(json.dumps(serializable), encoding="utf-8")


def _write_manifest(
    dst: Path,
    generated_on: str,
    hub_source: str,
    total: int,
    item_counts: dict[str, int],
    file_sizes: dict[str, int],
) -> None:
    manifest = {
        "generated_on": generated_on,
        "hub_source": hub_source,
        "total": total,
        "item_counts": item_counts,
        "file_sizes": file_sizes,
    }
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _sanity_check(dst: Path, offsets: dict[str, tuple[str, int, int]]) -> None:
    by_type: dict[str, list[str]] = {}
    for eid, (type_value, _, _) in offsets.items():
        by_type.setdefault(type_value, []).append(eid)

    for type_value, ids in by_type.items():
        path = dst / f"agent-{type_value}.json"
        buf = path.read_bytes()
        samples = [ids[0], ids[-1]] + random.sample(ids, min(3, len(ids)))
        for eid in samples:
            _, offset, length = offsets[eid]
            slice_bytes = buf[offset : offset + length]
            restored = json.loads(slice_bytes)
            if restored.get("item_id") != eid:
                sys.exit(
                    f"sanity check failed: offset for {eid} in {path.name} "
                    f"resolves to {restored.get('item_id')!r}"
                )


def _atomic_replace(src: Path, dst: Path) -> None:
    """Replace ``dst`` contents with ``src`` contents, preserving README.md and .gitattributes."""
    dst.mkdir(parents=True, exist_ok=True)
    preserved = {"README.md", ".gitattributes"}
    for existing in dst.iterdir():
        if existing.name in preserved:
            continue
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink()
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copyfile(item, target)


if __name__ == "__main__":
    raise SystemExit(main())
