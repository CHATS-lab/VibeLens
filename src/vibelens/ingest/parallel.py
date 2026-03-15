"""Parallel multi-file parsing using process pools.

JSON parsing and string manipulation are CPU-bound; the GIL blocks
threading from providing speedup.  ProcessPoolExecutor distributes
files across worker processes.  Results are serialised as plain dicts
across the process boundary (Pydantic pickling issues) and
reconstructed in the main process.
"""

import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from vibelens.models.message import Message
from vibelens.models.session import SessionSummary

logger = logging.getLogger(__name__)

MAX_WORKERS = 4
BATCH_SIZE = 50


def parse_files_parallel(
    parser_class_name: str,
    file_paths: list[Path],
    max_workers: int = MAX_WORKERS,
) -> list[tuple[SessionSummary, list[Message]]]:
    """Parse multiple files in parallel using process workers.

    Falls back to sequential parsing for fewer than BATCH_SIZE files,
    since pool creation overhead exceeds the parallelism gain.

    Args:
        parser_class_name: Name of the parser class to use (e.g. "ClaudeCodeParser").
        file_paths: List of file paths to parse.
        max_workers: Maximum number of worker processes.

    Returns:
        Combined list of (SessionSummary, messages) tuples from all files.
    """
    if len(file_paths) < BATCH_SIZE:
        return _parse_sequential(parser_class_name, file_paths)

    results: list[tuple[SessionSummary, list[Message]]] = []
    path_strings = [str(p) for p in file_paths]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_parse_file_worker, parser_class_name, path_str)
            for path_str in path_strings
        ]
        for future in futures:
            try:
                worker_results = future.result()
                for summary_dict, message_dicts in worker_results:
                    summary = SessionSummary.model_validate(summary_dict)
                    messages = [Message.model_validate(m) for m in message_dicts]
                    results.append((summary, messages))
            except Exception:
                logger.warning("Worker failed to parse file", exc_info=True)

    return results


def _parse_sequential(
    parser_class_name: str, file_paths: list[Path]
) -> list[tuple[SessionSummary, list[Message]]]:
    """Parse files sequentially — used when count is below BATCH_SIZE."""
    parser = _get_parser(parser_class_name)
    results: list[tuple[SessionSummary, list[Message]]] = []
    for path in file_paths:
        try:
            results.extend(parser.parse_file(path))
        except Exception:
            logger.warning("Failed to parse %s", path, exc_info=True)
    return results


def _parse_file_worker(
    parser_class_name: str, file_path_str: str
) -> list[tuple[dict, list[dict]]]:
    """Worker function executed in a subprocess.

    Returns plain dicts to avoid Pydantic pickling issues across
    the process boundary.

    Args:
        parser_class_name: Parser class name string.
        file_path_str: File path as string (Path isn't picklable across processes).

    Returns:
        List of (summary_dict, message_dicts) tuples.
    """
    parser = _get_parser(parser_class_name)
    file_path = Path(file_path_str)
    parsed = parser.parse_file(file_path)
    return [
        (summary.model_dump(), [msg.model_dump() for msg in messages])
        for summary, messages in parsed
    ]


def _get_parser(class_name: str):
    """Instantiate a parser by class name."""
    from vibelens.ingest.claude_code import ClaudeCodeParser
    from vibelens.ingest.codex import CodexParser
    from vibelens.ingest.dataclaw import DataclawParser
    from vibelens.ingest.gemini import GeminiParser

    registry = {
        "ClaudeCodeParser": ClaudeCodeParser,
        "CodexParser": CodexParser,
        "GeminiParser": GeminiParser,
        "DataclawParser": DataclawParser,
    }
    return registry[class_name]()
