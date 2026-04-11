"""Dashboard export service — CSV and JSON streaming responses."""

import csv
import io
import json

from fastapi.responses import StreamingResponse

from vibelens.services.dashboard.loader import load_filtered_trajectories
from vibelens.services.dashboard.stats import (
    SessionAggregate,
    aggregate_session,
    compute_dashboard_stats,
)

# Prefix for exported CSV/JSON filenames (date is appended at download time)
EXPORT_FILENAME_PREFIX = "vibelens-dashboard"
# Column headers for the dashboard CSV export
CSV_COLUMNS = [
    "session_id",
    "project_path",
    "agent",
    "model",
    "timestamp",
    "duration_s",
    "messages",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "tool_calls",
    "cost_usd",
]


def export_dashboard_csv(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
    agent_name: str | None = None,
) -> StreamingResponse:
    """Build CSV export from filtered trajectories.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.
        agent_name: Optional agent name filter.

    Returns:
        StreamingResponse with CSV content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token, agent_name
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)

    for traj in trajectories:
        agg = aggregate_session(traj)
        writer.writerow(_format_csv_row(traj.session_id, agg))

    buf.seek(0)
    filename = f"{EXPORT_FILENAME_PREFIX}-{timestamp}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def export_dashboard_json(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
    agent_name: str | None = None,
) -> StreamingResponse:
    """Build JSON export with dashboard stats.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.
        agent_name: Optional agent name filter.

    Returns:
        StreamingResponse with JSON content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token, agent_name
    )
    stats = compute_dashboard_stats(trajectories)
    payload = json.dumps(stats.model_dump(mode="json"), indent=2, ensure_ascii=False)

    filename = f"{EXPORT_FILENAME_PREFIX}-{timestamp}.json"
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _format_csv_row(session_id: str, agg: SessionAggregate) -> list:
    """Format a SessionAggregate into a CSV row matching CSV_COLUMNS order."""
    return [
        session_id,
        agg.project,
        agg.agent_name,
        agg.model,
        agg.timestamp.isoformat() if agg.timestamp else "",
        agg.duration,
        agg.messages,
        agg.input_tokens,
        agg.output_tokens,
        agg.cache_read_tokens,
        agg.cache_creation_tokens,
        agg.tool_calls,
        round(agg.cost_usd, 6) if agg.cost_usd else "",
    ]
