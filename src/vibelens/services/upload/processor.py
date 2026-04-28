"""Upload orchestration — stream, validate, extract, parse, store.

Handles the full upload lifecycle:
1. Stream incoming zip to ``{settings.upload_dir}/{upload_id}/{upload_id}.zip``
2. Validate and extract the archive
3. Discover session files using the agent-specific parser
4. Parse and store trajectories into ``{settings.upload_dir}/{upload_id}/``
5. Append upload metadata to ``{settings.upload_dir}/metadata.jsonl``
6. Clean up temporary extraction directory

Everything (zip, parsed trajectories, metadata) lives under
``settings.upload_dir``.  In demo mode the main DiskStore also
points to ``settings.upload_dir`` so uploaded sessions are
discovered automatically via rglob.
"""

import asyncio
import contextlib
import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.deps import (
    get_settings,
    is_demo_mode,
    register_upload_store,
    share_prior_upload_with_token,
)
from vibelens.ingest.anonymize.rule_anonymizer.anonymizer import RuleAnonymizer
from vibelens.ingest.parsers import get_parser
from vibelens.ingest.parsers.base import BaseParser
from vibelens.schemas.upload import UploadResult
from vibelens.services.dashboard.loader import (
    invalidate_cache as invalidate_dashboard_cache,
)
from vibelens.services.session.search import add_sessions_to_index
from vibelens.storage.trajectory.disk import DiskTrajectoryStore
from vibelens.utils import get_logger
from vibelens.utils.identifiers import generate_timestamped_id
from vibelens.utils.json import locked_jsonl_append
from vibelens.utils.timestamps import utc_now_iso
from vibelens.utils.zip import extract_zip, validate_zip

logger = get_logger(__name__)

# Temp directory name for ZIP extraction (deleted after parsing)
EXTRACTED_SUBDIR = "_extracted"
# Append-only log of all uploads under the upload directory
METADATA_FILENAME = "metadata.jsonl"

# First-match-wins rules dispatched by substring of ``str(exc)``. Used for
# parser-specific failure modes that arrive wrapped in generic exception
# types (e.g. Pydantic ValidationError carrying ``duplicate step IDs`` in
# its message body). Tried BEFORE the type-based table so a precise message
# wins over the generic class-based fallback.
_RULES_BY_MESSAGE_SUBSTRING: list[tuple[str, str]] = [
    (
        "duplicate step IDs",
        "Parser bug: the agent's session has duplicate step IDs. Please report "
        "the agent type — this needs a parser fix to be uploadable.",
    ),
    (
        "exceeds size limit",
        "Zip exceeds the upload size limit. Try splitting it or contact the admin "
        "to raise the limit.",
    ),
]

# First-match-wins rules dispatched by exception type. Either the concrete
# class (when we'd otherwise have to import a niche library type) or the
# class name as a string (avoids importing every concrete error class).
_RULES_BY_EXCEPTION_TYPE: list[tuple[type[Exception] | str, str]] = [
    (
        json.JSONDecodeError,
        "The session file isn't valid JSON. It may have been truncated mid-write.",
    ),
    (
        "UnicodeDecodeError",
        "The session file isn't UTF-8. The agent may use a different encoding.",
    ),
    (
        "FileNotFoundError",
        "Expected file is missing from the zip. Re-run the zip command.",
    ),
    (
        sqlite3.DatabaseError,
        "The SQLite database is corrupt or locked. Quit the agent and re-zip.",
    ),
    (
        "PermissionError",
        "Couldn't read the file (permission denied). Check the agent's data directory permissions.",
    ),
    (
        "ValidationError",
        "The parser produced data that doesn't match the expected schema. "
        "This is a parser bug — please report it with the agent type and any "
        "non-sensitive details below.",
    ),
    (
        "HTTPException",
        "Upload rejected by the server. See details below for the specific reason.",
    ),
]


def to_friendly_error(exc: Exception) -> dict:
    """Map a raw exception to ``{summary, details}`` for upload errors.

    ``summary`` is a one-line user-readable message; ``details`` is the
    raw ``str(exc)`` for the optional collapsible "raw error" panel.

    Lookup order: (1) substring matches against ``str(exc)`` for parser-
    specific failure modes that surface inside generic exception types;
    (2) class-based mappings; (3) generic fallback that names the exception
    class so the user at least knows the failure category.
    """
    message = str(exc) or exc.__class__.__name__
    for substring, summary in _RULES_BY_MESSAGE_SUBSTRING:
        if substring in message:
            return {"summary": summary, "details": message}
    for matcher, summary in _RULES_BY_EXCEPTION_TYPE:
        if isinstance(matcher, type) and isinstance(exc, matcher):
            return {"summary": summary, "details": message}
        if isinstance(matcher, str) and exc.__class__.__name__ == matcher:
            return {"summary": summary, "details": message}
    return {
        "summary": f"Unexpected {exc.__class__.__name__}. See details below.",
        "details": message,
    }


@dataclass
class _ProcessingContext:
    """Groups processing dependencies passed through the parse-store pipeline."""

    store: DiskTrajectoryStore
    parser: BaseParser
    anonymizer: RuleAnonymizer
    result: UploadResult


async def receive_zip(
    file: UploadFile, dest_dir: Path, expected_sha256: str | None = None
) -> tuple[Path, str]:
    """Stream an uploaded zip file to disk while accumulating its SHA-256.

    Writes to ``{dest_dir}/{dest_dir.name}.zip``. Returns the path plus
    the hex digest. If ``expected_sha256`` is provided, raises 400 on
    mismatch — protects against torn uploads where the client computed
    the hash but the bytes corrupted in transit.
    """
    settings = get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / f"{dest_dir.name}.zip"
    total_written = 0
    hasher = hashlib.sha256()

    with open(zip_path, "wb") as f:
        while True:
            chunk = await file.read(settings.upload.stream_chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            total_written += len(chunk)
            if total_written > settings.upload.max_zip_bytes:
                zip_path.unlink(missing_ok=True)
                max_mb = settings.upload.max_zip_bytes // (1024 * 1024)
                raise HTTPException(status_code=400, detail=f"File exceeds {max_mb} MB limit")
            f.write(chunk)

    sha = hasher.hexdigest()
    if expected_sha256 and expected_sha256.lower() != sha:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="X-Zip-Sha256 header doesn't match streamed bytes",
        )
    return zip_path, sha


def find_prior_upload(zip_sha256: str, agent_type: str) -> dict | None:
    """Look up a previously processed upload by ``(zip_sha256, agent_type)``.

    Returns the metadata.jsonl line dict if a prior matching upload exists
    *and* that upload actually stored some sessions. Failed uploads (parser
    crash, zero sessions, validation errors) are not considered cacheable —
    the user must be allowed to retry once we've fixed the underlying issue.

    Older lines without ``zip_sha256`` are treated as not-deduplicable
    (forward compatible).
    """
    settings = get_settings()
    metadata = settings.upload.dir / METADATA_FILENAME
    if not metadata.is_file():
        return None
    try:
        with open(metadata, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("zip_sha256") != zip_sha256:
                    continue
                if entry.get("agent_type") != agent_type:
                    continue
                totals = entry.get("totals") or {}
                if totals.get("sessions_parsed", 0) <= 0:
                    continue
                if totals.get("errors", 0) > 0:
                    continue
                return entry
    except OSError:
        return None
    return None


def load_prior_result(entry: dict) -> UploadResult | None:
    """Load the ``result.json`` referenced by a metadata.jsonl entry."""
    settings = get_settings()
    rel = entry.get("result_path")
    if not rel:
        return None
    full = settings.upload.dir / rel
    if not full.is_file():
        return None
    try:
        return UploadResult.model_validate_json(full.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def extract_and_discover(zip_path: Path, agent_type: str) -> list[Path]:
    """Validate zip, extract contents, and discover session files.

    Extraction goes into a ``_extracted`` sibling directory next to the zip.
    Reads size/count limits from application settings.

    Args:
        zip_path: Path to the uploaded zip file.
        agent_type: Agent CLI identifier for file discovery.

    Returns:
        List of discovered session file paths.
    """
    settings = get_settings()
    parser = get_parser(agent_type)
    allowed_extensions = parser.ALLOWED_EXTENSIONS
    validate_zip(
        zip_path=zip_path,
        max_zip_bytes=settings.upload.max_zip_bytes,
        max_extracted_bytes=settings.upload.max_extracted_bytes,
        max_file_count=settings.upload.max_file_count,
        allowed_extensions=allowed_extensions,
    )

    extracted_dir = zip_path.parent / EXTRACTED_SUBDIR
    extract_zip(zip_path=zip_path, dest_dir=extracted_dir, allowed_extensions=allowed_extensions)

    return parser.discover_session_files(extracted_dir)


def cleanup_extraction(extraction_dir: Path) -> None:
    """Remove a temporary extraction directory.

    The zip file itself is kept as a permanent archive;
    only the ``_extracted/`` subdirectory is removed.

    Args:
        extraction_dir: Path to the extraction directory to remove.
    """
    if extraction_dir.exists():
        shutil.rmtree(extraction_dir, ignore_errors=True)


async def process_zip(
    file: UploadFile,
    agent_type: str,
    session_token: str | None = None,
    expected_sha256: str | None = None,
) -> UploadResult:
    """Full upload orchestration: stream -> validate -> extract -> parse -> store.

    Everything (zip, parsed trajectories, metadata) goes under
    ``settings.upload_dir``.  The per-upload DiskStore at
    ``{upload_dir}/{upload_id}/`` tags each trajectory with
    ``_upload_id`` for visibility filtering.

    Args:
        file: Uploaded zip file.
        agent_type: Agent CLI identifier.
        session_token: Browser tab token for upload ownership (demo mode).
        expected_sha256: Optional client-provided SHA-256; verified against
            the streamed bytes. Mismatch → 400.

    Returns:
        UploadResult with counts and any errors.
    """
    settings = get_settings()
    if not is_demo_mode():
        raise HTTPException(status_code=400, detail="Uploads not supported in self-use mode")

    filename = file.filename or "upload.zip"
    result = UploadResult(files_received=1)
    upload_id = generate_timestamped_id()
    result.upload_id = upload_id
    token_short = session_token[:8] if session_token else "none"
    dest_dir = settings.upload.dir / upload_id

    logger.info(
        "process_zip START: file=%s agent=%s token=%s upload_id=%s upload_dir=%s",
        filename,
        agent_type,
        token_short,
        upload_id,
        settings.upload.dir,
    )

    try:
        zip_path, zip_sha256 = await receive_zip(
            file=file, dest_dir=dest_dir, expected_sha256=expected_sha256
        )
        result.zip_sha256 = zip_sha256
        logger.info(
            "Received zip: %s (%d bytes, sha256=%s)",
            zip_path,
            zip_path.stat().st_size,
            zip_sha256[:12],
        )

        # If we already imported this exact zip under the same agent, return
        # the prior result and discard the freshly streamed copy. This is
        # the body-side dedupe path: it kicks in even when the client didn't
        # send X-Zip-Sha256 (no extra hashing on the client). The header-
        # based early dedupe in api/upload.py avoids reading the body at all
        # when the client did pre-hash.
        prior = await asyncio.to_thread(find_prior_upload, zip_sha256, agent_type)
        if prior is not None:
            prior_result = await asyncio.to_thread(load_prior_result, prior)
            if prior_result is not None:
                logger.info(
                    "Deduplicated against prior upload %s (sha256=%s)",
                    prior.get("upload_id"),
                    zip_sha256[:12],
                )
                # Drop the freshly streamed dest_dir so we don't accumulate
                # duplicate copies of the same content.
                await asyncio.to_thread(shutil.rmtree, dest_dir, True)
                prior_result.deduplicated = True
                prior_result.original_upload_id = prior.get("upload_id")
                uploaded_at = prior.get("uploaded_at")
                if uploaded_at:
                    with contextlib.suppress(TypeError, ValueError):
                        prior_result.original_uploaded_at = datetime.fromisoformat(uploaded_at)
                # Make the prior data visible to *this* token too.
                if session_token and prior.get("upload_id"):
                    share_prior_upload_with_token(prior["upload_id"], session_token)
                return prior_result

        session_files = await asyncio.to_thread(
            extract_and_discover, zip_path=zip_path, agent_type=agent_type
        )
        logger.info(
            "Discovered %d session files in %s: %s",
            len(session_files),
            filename,
            [f.name for f in session_files[:10]],
        )

        # _upload_id tag lets the main store enforce visibility filtering
        tags: dict[str, str] = {"_upload_id": upload_id}
        if session_token:
            tags["_session_token"] = session_token
        upload_store = DiskTrajectoryStore(root=dest_dir, default_tags=tags)
        upload_store.initialize()

        ctx = _ProcessingContext(
            store=upload_store,
            parser=get_parser(agent_type),
            anonymizer=RuleAnonymizer(AnonymizeConfig(enabled=True)),
            result=result,
        )
        session_details = await asyncio.to_thread(
            _parse_and_store_files, session_files=session_files, ctx=ctx
        )

        logger.info(
            "Parse complete: sessions_parsed=%d steps_stored=%d skipped=%d errors=%d",
            result.sessions_parsed,
            result.steps_stored,
            result.skipped,
            len(result.errors),
        )

        upload_info = {
            "upload_id": upload_id,
            "agent_type": agent_type,
            "filename": filename,
            "session_token": session_token,
        }
        metadata = _build_upload_metadata(upload_info, session_details, result)
        # Idempotency: include zip_sha256 + result_path so repeated uploads
        # of the same content can dedupe via find_prior_upload().
        metadata["zip_sha256"] = result.zip_sha256
        metadata["uploaded_at"] = datetime.now(tz=timezone.utc).isoformat()
        result_rel_path = f"{upload_id}/result.json"
        metadata["result_path"] = result_rel_path

        # Persist the full result alongside the zip for later replay on dedupe.
        result_full_path = settings.upload.dir / result_rel_path
        await asyncio.to_thread(
            result_full_path.write_text, result.model_dump_json(indent=2), "utf-8"
        )

        await asyncio.to_thread(
            locked_jsonl_append, path=settings.upload.dir / METADATA_FILENAME, data=metadata
        )

        if session_token:
            register_upload_store(session_token, upload_store)
        new_session_ids = [d["session_id"] for d in session_details if "session_id" in d]
        add_sessions_to_index(new_session_ids, session_token)
        invalidate_dashboard_cache()
        logger.info("Registered upload store %s for token=%s", upload_store.root, token_short)
    except Exception as exc:
        logger.warning("Upload processing failed for %s: %s", filename, exc, exc_info=True)
        err = to_friendly_error(exc)
        err["filename"] = filename
        err["error"] = err["summary"]
        result.errors.append(err)
        # Failed upload is not usable. Drop the whole per-upload dir
        # (which contains the zip and any partial extraction) so failed
        # uploads do not accumulate under settings.upload.dir.
        await asyncio.to_thread(shutil.rmtree, dest_dir, True)
    else:
        # Success: keep the zip as an archive; only drop the extraction dir.
        extraction_dir = dest_dir / EXTRACTED_SUBDIR
        await asyncio.to_thread(cleanup_extraction, extraction_dir=extraction_dir)

    logger.info(
        "process_zip END: upload_id=%s result=parsed=%d stored=%d skipped=%d errors=%d",
        upload_id,
        result.sessions_parsed,
        result.steps_stored,
        result.skipped,
        len(result.errors),
    )
    return result


def _parse_and_store_files(session_files: list[Path], ctx: _ProcessingContext) -> list[dict]:
    """Parse discovered session files, anonymize, and persist via the disk store.

    Args:
        session_files: List of session file paths from discovery.
        ctx: Processing dependencies (parser, store, anonymizer, result).

    Returns:
        List of per-session detail dicts for the upload metadata.
    """
    session_details: list[dict] = []

    for file_path in session_files:
        try:
            trajectories = ctx.parser.parse(file_path=file_path)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", file_path.name, exc)
            err = to_friendly_error(exc)
            err["filename"] = file_path.name
            err["error"] = err["summary"]  # legacy field for older clients
            ctx.result.errors.append(err)
            continue

        if not trajectories:
            ctx.result.skipped += 1
            continue

        mains = [t for t in trajectories if not t.parent_trajectory_ref]
        if not mains:
            ctx.result.skipped += 1
            continue

        # Single session: one batch (main + sub-agents stored together).
        # Multi-conversation file (e.g. claude.ai export): one batch per main.
        batches = [trajectories] if len(mains) <= 1 else [[m] for m in mains]
        session_details.extend(_store_batches(batches, file_path, ctx))

    return session_details


def _store_batches(batches: list[list], file_path: Path, ctx: _ProcessingContext) -> list[dict]:
    """Anonymize and store one or more trajectory batches from a single file.

    Each batch is saved as an independent unit — a failure in one batch
    does not prevent subsequent batches from being stored.

    Args:
        batches: List of trajectory groups to store independently.
        file_path: Source file for error reporting and logging.
        ctx: Processing dependencies (store, anonymizer, result).

    Returns:
        List of session detail dicts for successfully stored batches.
    """
    details: list[dict] = []
    for batch in batches:
        anonymized = _anonymize_trajectories(batch, ctx)
        if not anonymized:
            continue
        try:
            ctx.store.save(trajectories=anonymized)
        except Exception as exc:
            logger.warning("Failed to store %s: %s", file_path.name, exc)
            err = to_friendly_error(exc)
            err["filename"] = file_path.name
            err["error"] = err["summary"]
            ctx.result.errors.append(err)
            continue

        main = next(t for t in anonymized if not t.parent_trajectory_ref)
        ctx.result.sessions_parsed += 1
        ctx.result.steps_stored += sum(len(t.steps) for t in anonymized)
        details.append(_build_session_detail(main.session_id, anonymized, file_path.name))

    if details:
        logger.info(
            "Stored %d session(s) from %s (upload %s)",
            len(details),
            file_path.name,
            ctx.store.root.name,
        )
    return details


def _anonymize_trajectories(trajectories: list, ctx: _ProcessingContext) -> list:
    """Anonymize a batch of trajectories and tag each with redaction metadata.

    Args:
        trajectories: Parsed trajectories from a single session file.
        ctx: Processing context with anonymizer and result for stats.

    Returns:
        List of anonymized trajectories with ``extra._anonymized`` and
        ``extra._anonymize_stats`` metadata tags.
    """
    anonymized_results = ctx.anonymizer.anonymize_batch(trajectories)
    anonymized_trajectories = []

    for anon_traj, anon_result in anonymized_results:
        if anon_traj.extra is None:
            anon_traj.extra = {}
        anon_traj.extra["_anonymized"] = True
        anon_traj.extra["_anonymize_stats"] = anon_result.model_dump()
        anonymized_trajectories.append(anon_traj)

        ctx.result.secrets_redacted += anon_result.secrets_redacted
        ctx.result.paths_anonymized += anon_result.paths_anonymized
        ctx.result.pii_redacted += anon_result.pii_redacted

    return anonymized_trajectories


def _build_session_detail(session_id: str, trajectories: list, source_file: str) -> dict:
    """Build a per-session detail dict for the upload metadata manifest.

    Args:
        session_id: Unique session identifier.
        trajectories: Stored trajectories (used for count computation).
        source_file: Original filename for provenance.

    Returns:
        Dict with session_id, trajectory_count, step_count, source_file.
    """
    return {
        "session_id": session_id,
        "trajectory_count": len(trajectories),
        "step_count": sum(len(t.steps) for t in trajectories),
        "source_file": source_file,
    }


def _build_upload_metadata(
    upload_info: dict, session_details: list[dict], result: UploadResult
) -> dict:
    """Build the upload manifest metadata dict.

    Args:
        upload_info: Identity fields (upload_id, agent_type, filename, session_token).
        session_details: Per-session detail dicts.
        result: UploadResult with aggregate counts.

    Returns:
        Metadata dict for appending to metadata.jsonl.
    """
    meta: dict = {
        "upload_id": upload_info["upload_id"],
        "timestamp": utc_now_iso(),
        "agent_type": upload_info["agent_type"],
        "original_filename": upload_info["filename"],
        "sessions": session_details,
        "totals": {
            "sessions_parsed": result.sessions_parsed,
            "steps_stored": result.steps_stored,
            "skipped": result.skipped,
            "errors": len(result.errors),
            "secrets_redacted": result.secrets_redacted,
            "paths_anonymized": result.paths_anonymized,
            "pii_redacted": result.pii_redacted,
        },
    }
    session_token = upload_info.get("session_token")
    if session_token:
        meta["session_token"] = session_token
    return meta
