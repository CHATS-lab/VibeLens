"""Pull endpoints for importing data from sources."""

from fastapi import APIRouter

from vibelens.api.deps import get_db, get_hf_source
from vibelens.models.requests import PullRequest, PullResult
from vibelens.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["pull"])


@router.post("/pull/huggingface")
async def pull_from_huggingface(request: PullRequest) -> PullResult:
    """Pull sessions from a HuggingFace dataclaw dataset."""
    hf_source = get_hf_source()
    conn = await get_db()
    try:
        return await hf_source.pull_repo(
            conn=conn,
            repo_id=request.repo_id,
            force_refresh=request.force_refresh,
        )
    finally:
        await conn.close()


@router.get("/pull/huggingface/repos")
async def list_huggingface_repos() -> list[dict]:
    """List locally cached HuggingFace dataclaw repos."""
    hf_source = get_hf_source()
    return hf_source.list_repos()
