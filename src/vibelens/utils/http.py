"""HTTP fetching utilities."""

import httpx

from vibelens.utils.log import get_logger

logger = get_logger(__name__)

DEFAULT_FETCH_TIMEOUT = 15


async def async_fetch_text(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT) -> str | None:
    """Async GET returning response text, or None on failure.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Response text, or None if the request failed.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code < 400:
                return resp.text
    except (httpx.HTTPError, httpx.TimeoutException):
        pass
    logger.warning("Failed to fetch content from %s", url)
    return None


def fetch_text(url: str, timeout: int = DEFAULT_FETCH_TIMEOUT) -> str | None:
    """Sync GET returning response text, or None on failure.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Response text, or None if the request failed.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, follow_redirects=True)
            if resp.status_code < 400:
                return resp.text
    except (httpx.HTTPError, httpx.TimeoutException):
        pass
    logger.warning("Failed to fetch content from %s", url)
    return None
