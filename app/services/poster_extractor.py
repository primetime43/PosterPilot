"""Poster candidate extraction from Plex media items.

Converts raw python-plexapi Poster objects into our PosterCandidate model,
optionally inspecting image dimensions via URL fetch.
"""

import logging
from typing import Optional

from app.models import PosterCandidate
from app.services.plex_client import PlexClient
from app.services.poster_scorer import ImageInspector

logger = logging.getLogger("posterpilot.poster_extractor")


class PosterExtractor:
    """Extracts and normalizes poster candidates from Plex items."""

    def __init__(self, plex_client: PlexClient, inspect_images: bool = False):
        self._plex = plex_client
        self._inspect_images = inspect_images
        self._inspector = ImageInspector()

    def extract(self, item) -> list[PosterCandidate]:
        """Extract all poster candidates for a media item.

        Args:
            item: A python-plexapi media item (Movie, Show, etc.)

        Returns:
            List of PosterCandidate objects with metadata populated.

        Notes on python-plexapi poster data:
            - poster.ratingKey: unique identifier for this poster
            - poster.thumb: relative URL path to the poster image
            - poster.provider: source/agent that provided the poster
              Values include: 'tmdb', 'tvdb', 'gracenote', 'local', or None
            - poster.selected: True if this is the currently active poster
        """
        raw_posters = self._plex.get_item_posters(item)
        if not raw_posters:
            return []

        candidates = []
        for poster in raw_posters:
            thumb_url = self._plex.get_poster_thumb_url(poster)
            is_selected = getattr(poster, "selected", False)

            # Skip non-selected posters that have no usable thumb URL.
            # These would result in recommending "nothing" as a replacement.
            if not thumb_url and not is_selected:
                continue

            candidate = PosterCandidate(
                rating_key=str(getattr(poster, "ratingKey", "")),
                thumb_url=thumb_url,
                provider=getattr(poster, "provider", None),
                selected=is_selected,
            )

            # Try to get image dimensions if inspection is enabled
            if self._inspect_images and thumb_url:
                dims = self._inspector.get_dimensions_from_url(thumb_url)
                if dims:
                    candidate.width, candidate.height = dims

            candidates.append(candidate)

        logger.debug(
            "Extracted %d poster candidates for '%s'", len(candidates), item.title
        )
        return candidates

    def find_current_poster(
        self, candidates: list[PosterCandidate]
    ) -> Optional[PosterCandidate]:
        """Find the currently selected poster from candidates."""
        for c in candidates:
            if c.selected:
                return c
        return None
