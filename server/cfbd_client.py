"""Thin client for the CollegeFootballData (CFBD) /plays endpoint with a
filesystem cache. A given (year, week, season_type, classification) is
immutable once the games are final, so we cache the raw JSON forever."""

import json
import os
import ssl
from pathlib import Path

import httpx
import truststore

CFBD_BASE_URL = "https://api.collegefootballdata.com"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

# Windows corporate networks often terminate TLS with a self-signed root CA
# that isn't in certifi's bundle but is trusted by the OS. Use the OS trust
# store instead of failing the handshake.
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class CFBDError(RuntimeError):
    pass


def _get(path: str, params: dict) -> list[dict]:
    api_key = os.environ.get("CFBD_API_KEY")
    if not api_key:
        raise CFBDError("CFBD_API_KEY is not set (check your .env file)")

    response = httpx.get(
        f"{CFBD_BASE_URL}{path}",
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
        verify=_SSL_CONTEXT,
    )

    if response.status_code == 401:
        raise CFBDError("CFBD rejected the API key (401) — check .env")
    response.raise_for_status()
    return response.json()


def _plays_cache_path(year: int, week: int, season_type: str, classification: str | None) -> Path:
    key = f"{year}_{week}_{season_type}_{classification or 'all'}.json"
    return CACHE_DIR / key


def get_plays(year: int, week: int, season_type: str, classification: str | None) -> list[dict]:
    """Return the raw list of play objects for a given week, using the cache
    when available.

    Note: CFBD's server-side `playType` filter on this endpoint does not
    reliably work (it can return zero rows for a type known to be present),
    so this always pulls the full week and callers filter locally."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _plays_cache_path(year, week, season_type, classification)

    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    params = {"year": year, "week": week, "seasonType": season_type}
    if classification:
        params["classification"] = classification

    plays = _get("/plays", params)
    cache_file.write_text(json.dumps(plays), encoding="utf-8")
    return plays


def get_play_types() -> list[dict]:
    """Return the authoritative play-type vocabulary (id/text/abbreviation)
    from CFBD, cached to disk since it rarely changes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "play_types.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    play_types = _get("/plays/types", {})
    cache_file.write_text(json.dumps(play_types), encoding="utf-8")
    return play_types
