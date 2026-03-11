"""Push endpoints for exporting data to targets."""

from fastapi import APIRouter

router = APIRouter(tags=["push"])


@router.post("/push/{target}")
async def push_to_target(target: str) -> dict:
    """Push selected sessions to a data target.

    Not yet implemented.
    """
    return {"target": target, "status": "not_implemented"}
