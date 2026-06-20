"""TMDB (The Movie Database) API client.

Fetches replacement posters directly from TMDB for items whose Plex
library has no good poster (e.g. a stale local frame grab with no agent
alternative). Uses the v3 API with an API key.

Poster candidates produced here use a rating_key of the form
``tmdb://<file_path>`` so the apply layer knows to upload them to Plex
via item.uploadPoster(url=...) instead of selecting an existing poster.
"""

import logging
from typing import Optional

from app.models import PosterCandidate

logger = logging.getLogger("posterpilot.tmdb_client")

API_BASE = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p"
# Prefix marking a candidate as a TMDB image to be uploaded on apply.
TMDB_RATING_PREFIX = "tmdb://"


def is_tmdb_candidate(rating_key: str) -> bool:
    return bool(rating_key) and rating_key.startswith(TMDB_RATING_PREFIX)


def upload_url_for(rating_key: str) -> Optional[str]:
    """Reconstruct the full-size TMDB image URL from a candidate key."""
    if not is_tmdb_candidate(rating_key):
        return None
    file_path = rating_key[len(TMDB_RATING_PREFIX):]
    return f"{IMG_BASE}/original{file_path}"


class TmdbClient:
    """Minimal TMDB v3 client for poster lookup."""

    def __init__(self, api_key: str, language: str = "en", preview_size: str = "w342"):
        self._api_key = api_key
        self._language = language or "en"
        self._preview_size = preview_size or "w342"

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def get_posters(
        self, tmdb_id: int, media_type: str = "movie", limit: int = 12
    ) -> list[PosterCandidate]:
        """Fetch poster candidates for a TMDB id.

        Returns candidates ranked by TMDB vote average, with preferred-language
        and language-agnostic (textless) posters first. Width/height come from
        TMDB metadata so no image download is needed to score them.
        """
        if not self.configured:
            return []

        endpoint = "tv" if media_type == "show" else "movie"
        url = f"{API_BASE}/{endpoint}/{tmdb_id}/images"
        params = {
            "api_key": self._api_key,
            # Include the user's language plus null (textless) posters.
            "include_image_language": f"{self._language},null",
        }

        try:
            import httpx

            with httpx.Client(timeout=10) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "TMDB images %s/%s returned %s",
                        endpoint, tmdb_id, resp.status_code,
                    )
                    return []
                data = resp.json()
        except Exception as e:
            logger.warning("TMDB request failed for %s %s: %s", endpoint, tmdb_id, e)
            return []

        posters = data.get("posters") or []

        def sort_key(p: dict):
            # Prefer the user's language, then textless, then anything;
            # within each, higher TMDB vote average wins.
            lang = p.get("iso_639_1")
            lang_rank = 0 if lang == self._language else (1 if lang is None else 2)
            return (lang_rank, -(p.get("vote_average") or 0))

        candidates: list[PosterCandidate] = []
        for p in sorted(posters, key=sort_key)[:limit]:
            file_path = p.get("file_path")
            if not file_path:
                continue
            candidates.append(
                PosterCandidate(
                    rating_key=f"{TMDB_RATING_PREFIX}{file_path}",
                    thumb_url=f"{IMG_BASE}/{self._preview_size}{file_path}",
                    provider="tmdb",
                    selected=False,
                    width=p.get("width"),
                    height=p.get("height"),
                )
            )

        logger.info(
            "TMDB returned %d poster candidates for %s/%s",
            len(candidates), endpoint, tmdb_id,
        )
        return candidates
