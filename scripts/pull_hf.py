"""Pull a dataclaw dataset from HuggingFace into VibeLens.

Usage:
    python scripts/pull_hf.py
    python scripts/pull_hf.py --repo-id org/dataset-name
    python scripts/pull_hf.py --force
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vibelens.config import load_settings
from vibelens.db import get_connection, init_db, query_sessions
from vibelens.sources.huggingface import HuggingFaceSource

DEFAULT_REPO_ID = "REXX-NEW/my-personal-claude-code-data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pull_hf")


async def run(repo_id: str, force: bool) -> None:
    """Download, parse, and store a HuggingFace dataclaw dataset."""
    settings = load_settings()
    await init_db(settings.db_path)

    data_dir = settings.db_path.parent
    source = HuggingFaceSource(data_dir, hf_token=settings.hf_token)

    conn = await get_connection()
    try:
        logger.info("Pulling %s (force=%s)", repo_id, force)
        result = await source.pull_repo(conn, repo_id, force_refresh=force)

        print(f"\n{'=' * 50}")
        print(f"  Repo:               {result.repo_id}")
        print(f"  Sessions imported:  {result.sessions_imported}")
        print(f"  Messages imported:  {result.messages_imported}")
        print(f"  Skipped:            {result.skipped}")
        print(f"{'=' * 50}")

        sessions = await query_sessions(conn, source_type="huggingface", limit=10000)
        projects = {s.project_name for s in sessions if s.project_name}

        print(f"\n  Total HF sessions:  {len(sessions)}")
        print(f"  Unique projects:    {len(projects)}")
        if projects:
            for p in sorted(projects)[:10]:
                print(f"    - {p}")
            if len(projects) > 10:
                print(f"    ... and {len(projects) - 10} more")
        print()

    finally:
        await conn.close()


def main() -> None:
    """Parse arguments and run the pull."""
    parser = argparse.ArgumentParser(description="Pull dataclaw dataset from HuggingFace")
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help=f"HuggingFace repo ID (default: {DEFAULT_REPO_ID})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-import even if cached",
    )
    args = parser.parse_args()
    asyncio.run(run(args.repo_id, args.force))


if __name__ == "__main__":
    main()
