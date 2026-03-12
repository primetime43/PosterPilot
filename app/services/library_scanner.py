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

    @staticmethod
    def _get_updated_timestamp(item) -> Optional[int]:
        """Get item's updatedAt as a unix timestamp (int)."""
        val = getattr(item, "updatedAt", None)
        if val is None:
            return None
        # plexapi returns datetime objects; convert to int timestamp
        if hasattr(val, "timestamp"):
            return int(val.timestamp())
        # Already numeric
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    # Providers considered low quality / likely broken
    _WEAK_PROVIDERS = {None, "", "gracenote", "local"}
    # Providers considered high quality
    _GOOD_PROVIDERS = {"tmdb", "tvdb"}

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
            plex_updated_at=self._get_updated_timestamp(item),
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

            # Check if current poster is an upload (Kometa, manual upload, etc.)
            if current and current.rating_key.startswith("upload://"):
                scan_item.is_uploaded = True

            # Detect likely broken posters
            self._detect_broken_poster(scan_item, current, ranked)

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
            elif scan_item.is_likely_broken:
                # Broken poster always gets a change recommendation
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

    def _detect_broken_poster(
        self,
        scan_item: ScanItem,
        current: Optional[PosterCandidate],
        ranked: list[PosterCandidate],
    ) -> None:
        """Detect if the current poster is likely broken or low quality.

        Metadata-based heuristics (no image downloading):
        1. No poster is selected among candidates — the item's thumb
           is not from the poster list, meaning it's likely an
           auto-generated video frame or a stale/orphaned poster
        2. Current poster has no/empty thumb URL
        3. Current poster is from Gracenote (known low quality)
        """
        has_good_alt = any(
            c.provider and c.provider.lower() in self._GOOD_PROVIDERS and c.thumb_url
            for c in ranked
        )

        if current is None:
            # No poster candidate is marked as selected. The item's
            # thumb is something outside the poster list — typically an
            # auto-generated video frame or an orphaned upload.
            scan_item.is_likely_broken = True
            scan_item.broken_reason = (
                "No poster is selected — current image is not from "
                "any known poster source (likely a video frame)"
            )
            return

        if not current.thumb_url:
            scan_item.is_likely_broken = True
            scan_item.broken_reason = "Current poster has no image URL"
            return

        current_provider = (current.provider or "").lower()

        # Gracenote posters are often low quality auto-picks
        if current_provider == "gracenote" and has_good_alt:
            scan_item.is_likely_broken = True
            scan_item.broken_reason = "Current poster is from Gracenote (often low quality)"

    def scan_library(
        self,
        library_key: str,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        previous_results: Optional[dict[str, "ScanItem"]] = None,
    ) -> list[ScanItem]:
        """Scan all items in a library using concurrent API calls.

        Uses a thread pool to call item.posters() in parallel, since
        the Plex API has no batch endpoint and each call is independent.

        If previous_results is provided (keyed by rating_key), items whose
        Plex updatedAt hasn't changed since the previous scan are carried
        forward without re-scanning, significantly speeding up repeat scans.
        """
        items = self._plex.get_library_items(library_key)
        total = len(items)

        # Split items into changed (need scanning) and unchanged (carry forward)
        items_to_scan: list[tuple[int, object]] = []
        results: list[Optional[ScanItem]] = [None] * total
        carried = 0

        if previous_results and not force_refresh:
            for i, item in enumerate(items):
                key = str(item.ratingKey)
                prev = previous_results.get(key)
                plex_updated = self._get_updated_timestamp(item)
                if (
                    prev
                    and prev.plex_updated_at is not None
                    and plex_updated is not None
                    and plex_updated == prev.plex_updated_at
                    and not prev.applied  # re-scan applied items to refresh state
                ):
                    # Carry forward — reset applied flag for fresh view
                    results[i] = prev
                    carried += 1
                else:
                    items_to_scan.append((i, item))
        else:
            items_to_scan = list(enumerate(items))

        scan_count = len(items_to_scan)
        logger.info(
            "Scanning library: %d total, %d to scan, %d unchanged (carried forward)",
            total, scan_count, carried,
        )

        # Report carried-forward items as already processed
        if carried and progress_callback:
            progress_callback(carried, total)

        processed = 0
        lock = threading.Lock()

        def _scan_at(index: int, item) -> tuple[int, ScanItem]:
            return index, self.scan_item(item, force_refresh)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_scan_at, idx, item): idx
                for idx, item in items_to_scan
            }
            for future in as_completed(futures):
                idx, scan_result = future.result()
                results[idx] = scan_result
                with lock:
                    processed += 1
                    if progress_callback:
                        progress_callback(carried + processed, total)

        # Report carried-forward items in initial progress
        if carried and progress_callback:
            # Already reported incrementally above; just ensure we hit total
            pass

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
