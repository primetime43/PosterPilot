"""Poster scoring and ranking engine.

Scores poster candidates based on configurable rules:
- Resolution quality
- Aspect ratio correctness (prefer 2:3 portrait posters)
- Provider/source priority
- Penalties for landscape, low-res, or unusual dimensions

The scoring system is extensible - add new scoring rules as methods
and register them in the score() method.
"""

import logging
import threading
from io import BytesIO
from typing import Optional

from app.config import ScoringConfig
from app.models import PosterCandidate

logger = logging.getLogger("posterpilot.poster_scorer")


class PosterScorer:
    """Scores and ranks poster candidates."""

    def __init__(self, config: ScoringConfig):
        self._config = config

    def score(self, candidate: PosterCandidate) -> PosterCandidate:
        """Score a single poster candidate. Modifies candidate in place."""
        breakdown: dict[str, float] = {}

        # Provider score
        provider_score = self._score_provider(candidate.provider)
        breakdown["provider"] = provider_score

        # Resolution score (requires width/height)
        resolution_score = self._score_resolution(candidate.width, candidate.height)
        breakdown["resolution"] = resolution_score

        # Aspect ratio score (requires width/height)
        aspect_score = self._score_aspect_ratio(candidate.width, candidate.height)
        breakdown["aspect_ratio"] = aspect_score

        # Landscape penalty
        landscape_penalty = self._penalty_landscape(candidate.width, candidate.height)
        breakdown["landscape_penalty"] = landscape_penalty

        # Minimum size penalty
        size_penalty = self._penalty_min_size(candidate.width, candidate.height)
        breakdown["size_penalty"] = size_penalty

        # Selected bonus - slight preference for currently selected poster
        # to avoid unnecessary changes
        selected_bonus = 0.5 if candidate.selected else 0.0
        breakdown["selected_bonus"] = selected_bonus

        total = (
            provider_score * self._config.provider_weight
            + resolution_score * self._config.resolution_weight
            + aspect_score * self._config.aspect_ratio_weight
            + landscape_penalty
            + size_penalty
            + selected_bonus
        )

        candidate.score = round(total, 2)
        candidate.score_breakdown = breakdown
        return candidate

    def rank(self, candidates: list[PosterCandidate]) -> list[PosterCandidate]:
        """Score and rank all candidates. Returns sorted list, best first."""
        for c in candidates:
            self.score(c)
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def _score_provider(self, provider: Optional[str]) -> float:
        """Score based on poster provider/source.

        Provider values observed in python-plexapi:
        - 'tmdb', 'tvdb', 'gracenote' - agent-supplied
        - 'local' - local media file
        - None or '' - uploaded or unknown source
        """
        if not provider:
            return 2.0  # Unknown/uploaded - neutral score

        provider_lower = provider.lower()
        priority = self._config.provider_priority
        for i, p in enumerate(priority):
            if provider_lower == p.lower():
                # Higher priority = higher score (first in list = best)
                return max(5.0 - i, 1.0)
        return 2.0  # Not in priority list

    def _score_resolution(
        self, width: Optional[int], height: Optional[int]
    ) -> float:
        """Score based on image resolution. Higher res = better score."""
        if width is None or height is None:
            return 2.0  # Can't determine, neutral score

        pixels = width * height
        if pixels >= 1000 * 1500:
            return 5.0  # Excellent
        elif pixels >= 600 * 900:
            return 4.0  # Good
        elif pixels >= 400 * 600:
            return 3.0  # Acceptable
        elif pixels >= 200 * 300:
            return 2.0  # Low
        return 1.0  # Very low

    def _score_aspect_ratio(
        self, width: Optional[int], height: Optional[int]
    ) -> float:
        """Score based on how close the aspect ratio is to ideal (2:3).

        Standard movie poster ratio is approximately 2:3 (0.667).
        """
        if width is None or height is None or height == 0:
            return 2.0

        ratio = width / height
        target = self._config.preferred_aspect_ratio
        tolerance = self._config.aspect_ratio_tolerance
        deviation = abs(ratio - target)

        if deviation <= tolerance * 0.3:
            return 5.0  # Very close to ideal
        elif deviation <= tolerance:
            return 3.5  # Acceptable range
        elif deviation <= tolerance * 2:
            return 2.0  # Somewhat off
        return 1.0  # Way off

    def _penalty_landscape(
        self, width: Optional[int], height: Optional[int]
    ) -> float:
        """Penalize landscape-oriented images (wider than tall)."""
        if not self._config.penalize_landscape:
            return 0.0
        if width is None or height is None:
            return 0.0
        if width > height:
            return self._config.landscape_penalty
        return 0.0

    def _penalty_min_size(
        self, width: Optional[int], height: Optional[int]
    ) -> float:
        """Penalize images below minimum acceptable size."""
        if width is None or height is None:
            return 0.0
        penalty = 0.0
        if width < self._config.min_width:
            penalty -= 3.0
        if height < self._config.min_height:
            penalty -= 3.0
        return penalty


class ImageInspector:
    """Lightweight image inspection using Pillow.

    Used to get width/height from poster images when not available
    from the Plex API metadata. Also provides brightness analysis
    for detecting broken/corrupt posters (dark video frame grabs).

    Image fetches share a single pooled HTTP client (see _get_client) so
    a full-library scan reuses keep-alive connections instead of opening
    and tearing one down per image — the latter exhausts sockets under the
    scanner's thread pool and fails partway through a large library.
    """

    _client = None
    _client_lock = threading.Lock()

    @classmethod
    def _get_client(cls):
        """Return a process-wide pooled httpx client, creating it once.

        Bounded connection limits keep the scanner from opening an
        unbounded number of sockets to the Plex server.
        """
        if cls._client is None:
            with cls._client_lock:
                if cls._client is None:
                    import httpx

                    cls._client = httpx.Client(
                        verify=False,
                        timeout=10,
                        limits=httpx.Limits(
                            max_connections=16,
                            max_keepalive_connections=8,
                        ),
                    )
        return cls._client

    @staticmethod
    def get_dimensions_from_bytes(data: bytes) -> Optional[tuple[int, int]]:
        """Get image dimensions from raw bytes."""
        try:
            from PIL import Image

            img = Image.open(BytesIO(data))
            return img.size  # (width, height)
        except Exception as e:
            logger.debug("Could not inspect image: %s", e)
            return None

    @staticmethod
    def get_dimensions_from_url(url: str, timeout: int = 10) -> Optional[tuple[int, int]]:
        """Fetch image from URL and get dimensions.

        Downloads only enough data to read the header when possible.
        """
        try:
            import httpx

            # Stream the response, only read header bytes
            with httpx.Client(timeout=timeout, verify=False) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return ImageInspector.get_dimensions_from_bytes(response.content)
        except Exception as e:
            logger.debug("Could not fetch/inspect image from URL: %s", e)
        return None

    @staticmethod
    def inspect_from_url(
        url: str, timeout: int = 10
    ) -> Optional[tuple[int, int, float]]:
        """Fetch an image ONCE and return (width, height, center_brightness).

        Combines dimension and brightness analysis into a single download
        so broken-poster detection costs one request per poster instead of
        two. Brightness is the median of the center 50% (0-255) to avoid
        corner overlay badges. Returns None if the image can't be fetched.

        Uses the shared pooled client so repeated scan inspections reuse
        keep-alive connections instead of churning sockets.
        """
        try:
            from PIL import Image

            client = ImageInspector._get_client()
            response = client.get(url, timeout=timeout)
            if response.status_code != 200:
                return None

            img = Image.open(BytesIO(response.content))
            w, h = img.size

            # Crop to center 50% to avoid corner overlays, then downscale.
            left, top = w // 4, h // 4
            center = img.crop((left, top, w - left, h - top))
            center = center.resize((32, 32)).convert("L")
            pixels = sorted(center.getdata())
            brightness = float(pixels[len(pixels) // 2])

            return w, h, brightness
        except Exception as e:
            logger.debug("Could not inspect image from URL: %s", e)
            return None

    @staticmethod
    def get_brightness_from_url(url: str, timeout: int = 5) -> Optional[float]:
        """Fetch image and return median brightness of the center region (0-255).

        Crops to the center 50% of the image before analysis to avoid
        overlay badges (Kometa, PMM) that sit in corners and inflate
        brightness of otherwise dark video frame grabs.

        Uses median instead of mean for robustness against bright outlier
        pixels from overlays.
        """
        try:
            import httpx
            from PIL import Image

            with httpx.Client(timeout=timeout, verify=False) as client:
                response = client.get(url)
                if response.status_code != 200:
                    return None

            img = Image.open(BytesIO(response.content))
            w, h = img.size

            # Crop to center 50% to avoid corner overlays
            left = w // 4
            top = h // 4
            right = w - left
            bottom = h - top
            center = img.crop((left, top, right, bottom))

            # Convert to grayscale and get pixel data
            center = center.resize((32, 32)).convert("L")
            pixels = sorted(center.getdata())
            median = pixels[len(pixels) // 2]
            return float(median)
        except Exception as e:
            logger.debug("Could not check brightness for URL: %s", e)
            return None
