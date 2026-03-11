"""Analysis endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["analysis"])


@router.get("/analysis/user-preference")
async def analyze_user_preference() -> dict:
    """Analyze user preferences across sessions.

    Not yet implemented.
    """
    return {"status": "not_implemented"}


@router.get("/analysis/agent-behavior")
async def analyze_agent_behavior() -> dict:
    """Analyze agent behavior patterns.

    Not yet implemented.
    """
    return {"status": "not_implemented"}
