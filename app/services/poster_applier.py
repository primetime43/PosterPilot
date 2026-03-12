"""Poster applier - applies poster changes to Plex items.

Handles the actual application of poster selections, including
dry-run mode, error handling, and result tracking.
"""

import logging
from typing import Optional

from app.models import ItemAction, ScanItem
from app.services.plex_client import PlexClient

logger = logging.getLogger("posterpilot.poster_applier")


class PosterApplier:
    """Applies poster changes to Plex media items."""

    def __init__(self, plex_client: PlexClient):
        self._plex = plex_client

    def apply_item(self, scan_item: ScanItem, dry_run: bool = True) -> ScanItem:
        """Apply the recommended poster change for a single item.

        Args:
            scan_item: The scan result with best_candidate set.
            dry_run: If True, only log what would happen without changing.

        Returns:
            Updated ScanItem with applied status.
        """
        if scan_item.action != ItemAction.CHANGE:
            return scan_item

        if not scan_item.best_candidate:
            scan_item.action = ItemAction.FAILED
            scan_item.error = "No best candidate available"
            return scan_item

        if dry_run:
            logger.info(
                "[DRY RUN] Would change poster for '%s' to %s (score: %.2f)",
                scan_item.title,
                scan_item.best_candidate.provider or "unknown",
                scan_item.best_candidate.score,
            )
            return scan_item

        try:
            # Get the actual Plex item
            section = self._plex.server.library.sectionByID(
                int(self._get_section_id(scan_item))
            ) if self._get_section_id(scan_item) else None

            # We need to find the item and its poster objects
            item = self._plex.server.fetchItem(int(scan_item.rating_key))
            posters = self._plex.get_item_posters(item)

            # Find the matching poster by rating_key
            target_poster = None
            for p in posters:
                if str(getattr(p, "ratingKey", "")) == scan_item.best_candidate.rating_key:
                    target_poster = p
                    break

            if target_poster is None:
                scan_item.action = ItemAction.FAILED
                scan_item.error = "Best candidate poster no longer available"
                return scan_item

            success = self._plex.set_poster(item, target_poster)
            if success:
                scan_item.applied = True
                logger.info(
                    "Applied poster for '%s' (provider: %s, score: %.2f)",
                    scan_item.title,
                    scan_item.best_candidate.provider or "unknown",
                    scan_item.best_candidate.score,
                )
            else:
                scan_item.action = ItemAction.FAILED
                scan_item.error = "setPoster call failed"

        except Exception as e:
            scan_item.action = ItemAction.FAILED
            scan_item.error = str(e)
            logger.error("Failed to apply poster for '%s': %s", scan_item.title, e)

        return scan_item

    def apply_batch(
        self, items: list[ScanItem], dry_run: bool = True
    ) -> list[ScanItem]:
        """Apply poster changes for a batch of items.

        Only processes items with action == CHANGE.
        """
        changeable = [i for i in items if i.action == ItemAction.CHANGE]
        logger.info(
            "Applying %d poster changes (dry_run=%s)", len(changeable), dry_run
        )

        for item in changeable:
            self.apply_item(item, dry_run)

        applied = sum(1 for i in changeable if i.applied)
        failed = sum(1 for i in changeable if i.action == ItemAction.FAILED)
        logger.info("Applied: %d, Failed: %d", applied, failed)

        return items

    def _get_section_id(self, scan_item: ScanItem) -> Optional[str]:
        """Extract section ID from scan item if available."""
        # This is a fallback; normally we use fetchItem by rating key
        return None
