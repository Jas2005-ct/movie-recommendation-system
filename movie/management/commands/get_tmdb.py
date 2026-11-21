import logging
import time

import requests
from django.conf import settings

TMDB_BASE = "https://api.themoviedb.org/3"
logger = logging.getLogger(__name__)


def tmdb_get(path, params=None, max_retries=3):
    """TMDB GET helper with retry/backoff for rate limits and server errors."""
    if params is None:
        params = {}
    params['api_key'] = settings.TMDB_API_KEY

    for attempt in range(max_retries):
        try:
            resp = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=12)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt < max_retries - 1:
                    retry_after = resp.headers.get('Retry-After')
                    try:
                        wait = float(retry_after) if retry_after else 2 ** attempt
                    except ValueError:
                        wait = 2 ** attempt
                    logger.warning(
                        "TMDB returned %s for %s; retrying in %ss",
                        resp.status_code, path, wait,
                    )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("TMDB request failed for %s: %s", path, exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return None
    return None
