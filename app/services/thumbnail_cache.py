"""Local thumbnail cache for poster images.

Downloads poster thumbnails from Plex and caches them on disk
to reduce repeated API calls when viewing scan results.
"""

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import requests

from app.config import get_data_dir

if TYPE_CHECKING:
    from app.config import Config

logger = logging.getLogger("posterpilot.thumbnail_cache")


def _get_cache_dir() -> Path:
    """Get the thumbnail cache directory."""
    p = get_data_dir() / "cache" / "thumbnails"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(url: str) -> str:
    """Generate a stable cache key by hashing the URL without the Plex token.

    Strips X-Plex-Token from the URL so that token rotation doesn't
    invalidate the entire cache.
    """
    cleaned = re.sub(r"[&?]X-Plex-Token=[^&]*", "", url)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


class ThumbnailCache:
    """Manages a local disk cache of poster thumbnail images."""

    def __init__(self, config: "Config"):
        self._cache_dir = _get_cache_dir()
        self._config = config

    @property
    def _max_age_secs(self) -> int:
        return self._config.app.cache_max_age_days * 24 * 60 * 60

    def get(self, url: str) -> Optional[Path]:
        """Return the cached file path if it exists and isn't stale."""
        key = _cache_key(url)
        # Check common image extensions
        for ext in (".jpg", ".png", ".webp"):
            path = self._cache_dir / f"{key}{ext}"
            if path.exists():
                age = time.time() - path.stat().st_mtime
                if age < self._max_age_secs:
                    return path
                # Stale — remove it
                path.unlink(missing_ok=True)
        return None

    def download(self, url: str, timeout: int = 15) -> Optional[Path]:
        """Download an image from the URL and cache it. Returns file path."""
        key = _cache_key(url)

        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()

            # Determine extension from content type
            content_type = resp.headers.get("Content-Type", "")
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            else:
                ext = ".jpg"

            path = self._cache_dir / f"{key}{ext}"
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug("Cached thumbnail: %s -> %s", key[:12], path.name)
            return path

        except Exception as e:
            logger.warning("Failed to cache thumbnail: %s", e)
            return None

    def get_or_download(self, url: str, timeout: int = 15) -> Optional[Path]:
        """Return cached file or download it."""
        cached = self.get(url)
        if cached:
            return cached
        return self.download(url, timeout)

    def clear(self) -> int:
        """Remove all cached thumbnails. Returns number of files deleted."""
        count = 0
        for f in self._cache_dir.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
                count += 1
        logger.info("Cleared %d cached thumbnails", count)
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        files = list(self._cache_dir.iterdir())
        image_files = [f for f in files if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in image_files)
        return {
            "count": len(image_files),
            "size_bytes": total_bytes,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "cache_dir": str(self._cache_dir),
        }
