"""Push endpoints for exporting data to targets."""

import logging

from fastapi import APIRouter, HTTPException

from vibelens.api.deps import get_local_source, get_mongodb_target
from vibelens.models.requests import PushRequest, PushResult
from vibelens.models.session import DataTargetType, SessionDetail

logger = logging.getLogger(__name__)

router = APIRouter(tags=["push"])


@router.post("/push/mongodb", response_model=PushResult)
async def push_to_mongodb(body: PushRequest) -> PushResult:
    """Push selected sessions to MongoDB via LocalSource."""
    if body.target != DataTargetType.MONGODB:
        raise HTTPException(status_code=400, detail="This endpoint only supports MongoDB target")

    try:
        target = get_mongodb_target()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    source = get_local_source()
    sessions: list[SessionDetail] = []
    for session_id in body.session_ids:
        detail = source.get_session(session_id)
        if detail is None:
            logger.warning("Session %s not found, skipping", session_id)
            continue
        sessions.append(detail)

    return await target.push_sessions(sessions)
