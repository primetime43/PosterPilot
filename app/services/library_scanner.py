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
from app.services.poster_scorer import ImageInspector, PosterScorer
from app.services.tmdb_client import TmdbClient

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
        self._inspector = ImageInspector()
        self._tmdb = TmdbClient(
            config.tmdb.api_key,
            language=config.tmdb.language,
            preview_size=config.tmdb.preview_size,
        ) if config.tmdb.enabled else TmdbClient("")

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

    def scan_item_detect_only(self, item) -> ScanItem:
        """Phase 1: decide whether an item's CURRENT poster is broken,
        WITHOUT calling the expensive per-item posters() API.

        Only the current thumb is inspected — a single small transcode
        fetch. Items that look broken are resolved later in phase 2, where
        their replacement candidates are actually loaded. Healthy items
        finish here with action=SKIP and no candidate list (those are
        fetched lazily if the user opens the item).
        """
        scan_item = ScanItem(
            rating_key=str(item.ratingKey),
            title=item.title,
            year=getattr(item, "year", None),
            item_type=item.type,
            current_poster_url=self._plex.get_item_thumb_url(item),
            is_locked=self._plex.is_poster_locked(item),
            plex_updated_at=self._get_updated_timestamp(item),
        )

        try:
            broken, reason = self._inspect_thumb(item)
            if broken:
                scan_item.is_likely_broken = True
                scan_item.broken_reason = reason
            scan_item.action = ItemAction.SKIP
        except Exception as e:
            scan_item.action = ItemAction.FAILED
            scan_item.error = str(e)
            logger.error("Error detecting '%s': %s", item.title, e)

        return scan_item

    def _inspect_thumb(self, item) -> tuple[bool, Optional[str]]:
        """Inspect the current poster's pixels and report if it's broken.

        Fetches a SMALL, aspect-preserving transcode of the current thumb
        (a few KB) and flags landscape orientation, a far-off aspect ratio,
        or — as a conservative last resort — a very dark image. This is the
        only network call phase 1 makes per item, replacing the much
        heavier posters() call the old scan did for every title.

        Note: because phase 1 never calls posters(), provider-based
        heuristics (e.g. flagging correctly-shaped Gracenote posters) no
        longer run. A bad poster that happens to be portrait-shaped and
        bright won't be flagged — but real frame grabs/backdrops are
        landscape or wrong-shaped and are still caught here.
        """
        cfg = self._config.scoring
        inspect_url = self._plex.get_item_inspect_url(item)
        if not inspect_url:
            return False, None

        result = self._inspector.inspect_from_url(inspect_url)
        if not result:
            return False, None
        w, h, brightness = result
        if h <= 0:
            return False, None

        # Landscape — frame grab or backdrop, not poster art.
        if w > h:
            return True, (
                f"Current poster is landscape ({w}x{h}) — likely a "
                "video frame or backdrop, not poster art"
            )

        # Aspect ratio far from the ~2:3 target.
        ratio = w / h
        if abs(ratio - cfg.preferred_aspect_ratio) > cfg.broken_aspect_tolerance:
            return True, (
                f"Current poster has the wrong shape (ratio {ratio:.2f}, "
                f"expected ~{cfg.preferred_aspect_ratio:.2f})"
            )

        # Conservative last resort: correctly-shaped but very dark.
        if brightness < cfg.min_brightness:
            return True, (
                f"Current poster is very dark (brightness {brightness:.0f}/255) "
                "— likely a dark video frame"
            )

        return False, None

    def build_candidates(self, item):
        """Load and rank poster candidates for an item (calls posters()).

        Returns (ranked_candidates, current_poster, best_candidate). Shared
        by phase-2 resolution and the on-demand candidate endpoint so the
        per-item posters() call lives in exactly one place.
        """
        candidates = self._extractor.extract(item)
        if not candidates:
            return [], None, None
        ranked = self._scorer.rank(candidates)
        current = self._extractor.find_current_poster(ranked)
        best = next((c for c in ranked if c.thumb_url), None)
        return ranked, current, best

    def resolve_item(self, item, scan_item: ScanItem) -> ScanItem:
        """Phase 2: load replacement candidates for a flagged-broken item
        and recommend the best non-current poster.

        Plex's own poster list is tried first; when it has no good
        alternative (the common case for broken posters — Plex only holds
        the bad local image), TMDB is queried directly for real artwork.
        Only runs for items phase 1 marked broken, so this work is spent on
        the handful that actually need a fix.
        """
        try:
            ranked, current, _best = self.build_candidates(item)
            scan_item.current_poster = current
            if current and current.rating_key.startswith("upload://"):
                scan_item.is_uploaded = True

            # Pull real posters straight from TMDB and merge them in. These
            # carry width/height from TMDB metadata, so the scorer ranks
            # them on resolution/aspect just like inspected Plex posters.
            tmdb_candidates = self._fetch_tmdb_candidates(item)
            combined = self._scorer.rank(ranked + tmdb_candidates)
            scan_item.all_candidates = combined

            # Never recommend the current (broken) poster as its own fix:
            # pick the best-ranked candidate that isn't the current one and
            # has a usable image.
            current_key = current.rating_key if current else None
            pool = [
                c for c in combined
                if c.thumb_url and c.rating_key != current_key
            ]
            if not pool:
                scan_item.action = ItemAction.NO_ALTERNATIVES
                return scan_item

            scan_item.best_candidate = pool[0]
            scan_item.action = ItemAction.CHANGE

        except Exception as e:
            scan_item.action = ItemAction.FAILED
            scan_item.error = str(e)
            logger.error("Error resolving '%s': %s", scan_item.title, e)

        return scan_item

    def _fetch_tmdb_candidates(self, item) -> list:
        """Fetch poster candidates from TMDB for an item, if configured.

        Resolves the TMDB id from the item's external ids, falling back to
        TMDB's /find endpoint for legacy IMDb/TVDB-agent items that don't
        carry a TMDB id directly.
        """
        if not self._tmdb.configured:
            return []

        media_type = getattr(item, "type", "movie")
        ids = self._plex.get_external_ids(item)
        tmdb_id = ids.get("tmdb")

        if not tmdb_id and ids.get("imdb"):
            tmdb_id = self._tmdb.find_by_external_id(ids["imdb"], "imdb_id", media_type)
        if not tmdb_id and ids.get("tvdb"):
            tmdb_id = self._tmdb.find_by_external_id(
                str(ids["tvdb"]), "tvdb_id", media_type
            )

        # Last resort for items Plex left unmatched (guid local://...) or
        # mismatched to a dead IMDb id: search TMDB by title + year.
        if not tmdb_id:
            year = getattr(item, "year", None)
            tmdb_id = self._tmdb.search(item.title, year, media_type)
            if tmdb_id:
                logger.info(
                    "TMDB title-search matched '%s' (%s) -> %s",
                    item.title, year or "no year", tmdb_id,
                )

        if not tmdb_id:
            logger.info(
                "No TMDB match for '%s' (external ids: %s) — no TMDB posters",
                item.title, ids or "none",
            )
            return []

        return self._tmdb.get_posters(tmdb_id, media_type=media_type)

    def scan_library(
        self,
        library_key: str,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        previous_results: Optional[dict[str, "ScanItem"]] = None,
    ) -> list[ScanItem]:
        """Scan a library in two phases for speed.

        Phase 1 (detect): inspect every item's current poster with one
        small thumb fetch and flag the broken ones. No posters() calls.
        Phase 2 (resolve): call the expensive item.posters() only for the
        flagged-broken items, to load and rank replacement candidates.

        This avoids the old cost of one posters() call per title — the bulk
        of the library never needs it. Healthy items finish phase 1 with
        action=SKIP and an empty candidate list; their alternatives are
        loaded on demand via build_candidates if the user opens the item.

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
        items_by_index = dict(items_to_scan)

        # ── Phase 1: detect broken posters (no posters() calls) ──
        # Each item costs only one small thumb fetch. This is the bulk of
        # the work and drives the progress bar.
        def _detect_at(index: int, item) -> tuple[int, ScanItem]:
            return index, self.scan_item_detect_only(item)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_detect_at, idx, item): idx
                for idx, item in items_to_scan
            }
            for future in as_completed(futures):
                idx, scan_result = future.result()
                results[idx] = scan_result
                with lock:
                    processed += 1
                    if progress_callback:
                        progress_callback(carried + processed, total)

        # ── Phase 2: resolve only the broken items (calls posters()) ──
        # The expensive per-item API call is now spent on just the handful
        # that need a replacement, instead of the whole library.
        broken_indices = [
            idx for idx in items_by_index
            if results[idx] is not None and results[idx].is_likely_broken
        ]
        logger.info(
            "Phase 1 done: %d broken of %d scanned — resolving candidates",
            len(broken_indices), scan_count,
        )

        def _resolve_at(index: int) -> None:
            self.resolve_item(items_by_index[index], results[index])

        if broken_indices:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                resolve_futures = [
                    pool.submit(_resolve_at, idx) for idx in broken_indices
                ]
                for future in as_completed(resolve_futures):
                    future.result()

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
