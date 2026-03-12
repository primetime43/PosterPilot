"""Library scanner - orchestrates scanning items and determining actions.

Coordinates the poster extractor, scorer, and produces ScanItem results
for each media item in a Plex library.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from app.config import Config
from app.models import ItemAction, PosterCandidate, ScanItem
from app.services.plex_client import PlexClient
from app.services.poster_extractor import PosterExtractor
from app.services.poster_scorer import PosterScorer

# Number of concurrent Plex API calls for poster fetching.
# Too high may overwhelm the Plex server; 8 is a safe default.
MAX_WORKERS = 8

logger = logging.getLogger("posterpilot.library_scanner")


class LibraryScanner:
    """Scans Plex library items and determines poster actions."""

    def __init__(self, plex_client: PlexClient, config: Config):
        self._plex = plex_client
        self._config = config
        self._extractor = PosterExtractor(plex_client, inspect_images=False)
        self._scorer = PosterScorer(config.scoring)

    def scan_item(self, item, force_refresh: bool = False) -> ScanItem:
        """Scan a single media item and determine the best poster action.

        Always extracts and scores poster candidates so the user can
        see what's available. The action recommendation accounts for
        locks, force-refresh, and score differences.
        """
        is_locked = self._plex.is_poster_locked(item)

        scan_item = ScanItem(
            rating_key=str(item.ratingKey),
            title=item.title,
            year=getattr(item, "year", None),
            item_type=item.type,
            current_poster_url=self._plex.get_item_thumb_url(item),
            is_locked=is_locked,
        )

        try:
            # Always extract poster candidates so the user can see them
            candidates = self._extractor.extract(item)
            if not candidates:
                scan_item.action = ItemAction.NO_ALTERNATIVES
                return scan_item

            if len(candidates) <= 1:
                scan_item.action = ItemAction.NO_ALTERNATIVES
                scan_item.all_candidates = candidates
                return scan_item

            # Score and rank candidates
            ranked = self._scorer.rank(candidates)
            scan_item.all_candidates = ranked

            # Find current poster
            current = self._extractor.find_current_poster(ranked)
            scan_item.current_poster = current

            # Best candidate is the top-ranked one that has a valid thumb URL.
            # Never recommend switching to a poster with no image.
            best = None
            for c in ranked:
                if c.thumb_url:
                    best = c
                    break
            if not best:
                scan_item.action = ItemAction.NO_ALTERNATIVES
                return scan_item
            scan_item.best_candidate = best

            # Determine action based on score comparison
            if current and best.rating_key == current.rating_key:
                # Current poster is already the best
                if force_refresh:
                    scan_item.action = ItemAction.CHANGE
                else:
                    scan_item.action = ItemAction.SKIP
            elif self._config.app.force_replace or force_refresh:
                scan_item.action = ItemAction.CHANGE
            elif current is None:
                # No current poster identified in candidates — recommend best
                scan_item.action = ItemAction.CHANGE
            else:
                # Current is not the best — recommend change only if
                # the score difference is meaningful (avoids churn)
                score_diff = best.score - current.score
                if score_diff > 0.5:
                    scan_item.action = ItemAction.CHANGE
                else:
                    scan_item.action = ItemAction.SKIP

        except Exception as e:
            scan_item.action = ItemAction.FAILED
            scan_item.error = str(e)
            logger.error("Error scanning '%s': %s", item.title, e)

        return scan_item

    def scan_library(
        self,
        library_key: str,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[ScanItem]:
        """Scan all items in a library using concurrent API calls.

        Uses a thread pool to call item.posters() in parallel, since
        the Plex API has no batch endpoint and each call is independent.
        """
        items = self._plex.get_library_items(library_key)
        total = len(items)
        logger.info("Scanning library with %d items (%d workers)", total, MAX_WORKERS)

        # Pre-allocate results in order; fill them as futures complete
        results: list[Optional[ScanItem]] = [None] * total
        processed = 0
        lock = threading.Lock()

        def _scan_at(index: int, item) -> tuple[int, ScanItem]:
            return index, self.scan_item(item, force_refresh)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_scan_at, i, item): i
                for i, item in enumerate(items)
            }
            for future in as_completed(futures):
                idx, scan_result = future.result()
                results[idx] = scan_result
                with lock:
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total)

        # Filter out any None (shouldn't happen but be safe)
        final = [r for r in results if r is not None]

        changes = sum(1 for r in final if r.action == ItemAction.CHANGE)
        skips = sum(1 for r in final if r.action == ItemAction.SKIP)
        locked = sum(1 for r in final if r.action == ItemAction.LOCKED)
        fails = sum(1 for r in final if r.action == ItemAction.FAILED)
        logger.info(
            "Scan complete: %d changes, %d skips, %d locked, %d failures",
            changes, skips, locked, fails,
        )

        return final
