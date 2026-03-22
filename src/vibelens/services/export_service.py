"""Dashboard export service — CSV and JSON streaming responses."""

import csv
import io
import json

from fastapi.responses import StreamingResponse

from vibelens.analysis.dashboard_stats import compute_dashboard_stats
from vibelens.models.trajectories import Trajectory
from vibelens.services.dashboard_service import load_filtered_trajectories


def export_dashboard_csv(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
) -> StreamingResponse:
    """Build CSV export from filtered trajectories.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.

    Returns:
        StreamingResponse with CSV content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "session_id",
            "project_path",
            "model",
            "timestamp",
            "duration_s",
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "messages",
        ]
    )

    for traj in trajectories:
        row = _build_csv_row(traj)
        writer.writerow(row)

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="vibelens-dashboard-{timestamp}.csv"',
        },
    )


def export_dashboard_json(
    project_path: str | None,
    date_from: str | None,
    date_to: str | None,
    session_token: str | None,
    timestamp: str,
) -> StreamingResponse:
    """Build JSON export with dashboard stats.

    Args:
        project_path: Optional project path filter.
        date_from: Optional start date (YYYY-MM-DD).
        date_to: Optional end date (YYYY-MM-DD).
        session_token: Browser tab token for upload scoping.
        timestamp: YYYYMMDDHHMMSS string for the filename.

    Returns:
        StreamingResponse with JSON content.
    """
    trajectories, _meta = load_filtered_trajectories(
        project_path, date_from, date_to, session_token
    )
    stats = compute_dashboard_stats(trajectories)
    payload = json.dumps(stats.model_dump(mode="json"), indent=2, ensure_ascii=False)

    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="vibelens-dashboard-{timestamp}.json"',
        },
    )


def _build_csv_row(traj: Trajectory) -> list:
    """Build a single CSV row from a trajectory."""
    input_tok = 0
    output_tok = 0
    tool_count = 0
    for step in traj.steps:
        if step.metrics:
            input_tok += step.metrics.prompt_tokens
            output_tok += step.metrics.completion_tokens
        tool_count += len(step.tool_calls)

    duration = 0
    if traj.final_metrics and traj.final_metrics.duration > 0:
        duration = traj.final_metrics.duration
    elif len(traj.steps) >= 2:
        first_ts = traj.steps[0].timestamp
        last_ts = traj.steps[-1].timestamp
        if first_ts and last_ts:
            duration = max(0, int((last_ts - first_ts).total_seconds()))

    model = (traj.agent.model_name if traj.agent else None) or ""
    if not model:
        for step in traj.steps:
            if step.model_name:
                model = step.model_name
                break

    return [
        traj.session_id,
        traj.project_path or "",
        model,
        traj.timestamp.isoformat() if traj.timestamp else "",
        duration,
        input_tok,
        output_tok,
        tool_count,
        len(traj.steps),
    ]
