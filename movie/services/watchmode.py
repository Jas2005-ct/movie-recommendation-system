"""Watchmode API client used only by management commands.

Base URL: https://api.watchmode.com/v1
Auth: X-API-Key header (preferred over query-string credentials).

No view imports this module — all user-facing data still comes from the local DB.
"""

import logging
import time

import requests
from django.conf import settings

BASE_URL = "https://api.watchmode.com/v1"
logger = logging.getLogger(__name__)


class WatchmodeError(Exception):
    """Raised when the Watchmode API cannot be used."""


def _get(path, params=None, max_retries=3):
    api_key = settings.WATCHMODE_API_KEY
    if not api_key:
        raise WatchmodeError(
            'WATCHMODE_API_KEY is not set. Add it to .env or use MOVIE_DATA_PROVIDER=tmdb.'
        )

    params = dict(params or {})
    url = f"{BASE_URL}{path}"

    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                params=params,
                headers={'X-API-Key': api_key},
                timeout=15,
            )
            if response.status_code == 401:
                raise WatchmodeError('Watchmode rejected the API key (HTTP 401).')
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < max_retries - 1:
                    retry_after = response.headers.get('Retry-After')
                    try:
                        wait = float(retry_after) if retry_after else 2 ** attempt
                    except ValueError:
                        wait = 2 ** attempt
                    wait = min(wait, 15)
                    logger.warning(
                        'Watchmode returned %s for %s; retrying in %ss',
                        response.status_code, path, wait,
                    )
                    time.sleep(wait)
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.warning('Watchmode request failed for %s: %s', path, exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue

    raise WatchmodeError(f'Watchmode request failed for {path} after retries.')


def status():
    """Account quota status. Costs 0 credits."""
    return _get('/status/')


def genres():
    """Genre directory with Watchmode IDs, names and TMDB IDs (1 credit)."""
    return _get('/genres/')


def list_titles(**params):
    """Paginated lightweight title list (1 credit per page)."""
    return _get('/list-titles/', params)


def title_details(title_id):
    """Full metadata for a Watchmode title ID (1 credit)."""
    return _get(f'/title/{title_id}/details/')


def title_cast_crew(title_id):
    """Cast and crew for a Watchmode title ID (1 credit)."""
    return _get(f'/title/{title_id}/cast-crew/')


def person(person_id):
    """Person metadata including gender and TMDB ID (1 credit)."""
    return _get(f'/person/{person_id}/')
