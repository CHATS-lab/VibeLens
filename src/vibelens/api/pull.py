"""Pull endpoints for importing data from sources."""

from fastapi import APIRouter

router = APIRouter(tags=["pull"])


@router.post("/pull/huggingface")
async def pull_from_huggingface() -> dict:
    """Pull sessions from a HuggingFace dataclaw dataset.

    Not yet implemented.
    """
    return {"status": "not_implemented"}


@router.get("/pull/huggingface/repos")
async def list_huggingface_repos() -> list:
    """List available HuggingFace dataclaw repos.

    Not yet implemented.
    """
    return []
