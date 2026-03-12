"""Persistent ignore list for Plex media items.

Items on this list are skipped during scans — no poster changes
will be suggested for them.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from app.config import get_data_dir

logger = logging.getLogger("posterpilot.ignore_list")


class IgnoreList:
    """Manages a set of ignored Plex item rating keys."""

    def __init__(self) -> None:
        self._path = get_data_dir() / "ignore_list.json"
        self._items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                # Support both old list format and new dict format
                if isinstance(data, list):
                    self._items = {k: {} for k in data}
                elif isinstance(data, dict):
                    self._items = data
            except Exception as e:
                logger.error("Failed to load ignore list: %s", e)
                self._items = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._items, indent=2), encoding="utf-8"
        )

    def is_ignored(self, rating_key: str) -> bool:
        return rating_key in self._items

    def add(self, rating_key: str, title: Optional[str] = None) -> None:
        self._items[rating_key] = {"title": title}
        self._save()
        logger.info("Added to ignore list: %s (%s)", rating_key, title)

    def add_bulk(self, items: list[dict]) -> int:
        """Add multiple items. Each dict has 'rating_key' and optional 'title'."""
        count = 0
        for item in items:
            key = item.get("rating_key")
            if key and key not in self._items:
                self._items[key] = {"title": item.get("title")}
                count += 1
        if count:
            self._save()
            logger.info("Bulk added %d items to ignore list", count)
        return count

    def remove(self, rating_key: str) -> bool:
        if rating_key in self._items:
            del self._items[rating_key]
            self._save()
            logger.info("Removed from ignore list: %s", rating_key)
            return True
        return False

    def clear(self) -> None:
        self._items.clear()
        self._save()
        logger.info("Cleared ignore list")

    def get_all(self) -> dict[str, dict]:
        return dict(self._items)

    def count(self) -> int:
        return len(self._items)
