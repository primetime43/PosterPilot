"""Background task manager for long-running scan and apply operations.

Uses threading to run scans and applies in the background while
providing progress updates via polling.

Completed scan jobs are cached to disk as JSON so they persist
across application restarts.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import Config, get_data_dir
from app.models import (
    ApplyJob,
    ItemAction,
    PosterCandidate,
    ScanItem,
    ScanJob,
    ScanStatus,
)
from app.services.library_scanner import LibraryScanner
from app.services.plex_client import PlexClient
from app.services.poster_applier import PosterApplier

logger = logging.getLogger("posterpilot.task_manager")


def _get_cache_dir() -> Path:
    """Get the scan cache directory."""
    p = get_data_dir() / "scans"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _serialize_candidate(c: Optional[PosterCandidate]) -> Optional[dict]:
    if c is None:
        return None
    return {
        "rating_key": c.rating_key,
        "thumb_url": c.thumb_url,
        "provider": c.provider,
        "selected": c.selected,
        "score": c.score,
        "width": c.width,
        "height": c.height,
        "score_breakdown": c.score_breakdown,
    }


def _deserialize_candidate(d: Optional[dict]) -> Optional[PosterCandidate]:
    if d is None:
        return None
    return PosterCandidate(
        rating_key=d["rating_key"],
        thumb_url=d["thumb_url"],
        provider=d.get("provider"),
        selected=d.get("selected", False),
        score=d.get("score", 0.0),
        width=d.get("width"),
        height=d.get("height"),
        score_breakdown=d.get("score_breakdown", {}),
    )


def _serialize_job(job: ScanJob) -> dict:
    """Serialize a ScanJob to a JSON-compatible dict."""
    return {
        "job_id": job.job_id,
        "library_key": job.library_key,
        "library_title": job.library_title,
        "status": job.status.value,
        "total_items": job.total_items,
        "processed_items": job.processed_items,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
        "force_refresh": job.force_refresh,
        "items": [
            {
                "rating_key": i.rating_key,
                "title": i.title,
                "year": i.year,
                "item_type": i.item_type,
                "current_poster_url": i.current_poster_url,
                "current_poster": _serialize_candidate(i.current_poster),
                "best_candidate": _serialize_candidate(i.best_candidate),
                "all_candidates": [_serialize_candidate(c) for c in i.all_candidates],
                "action": i.action.value,
                "is_locked": i.is_locked,
                "is_uploaded": i.is_uploaded,
                "is_likely_broken": i.is_likely_broken,
                "broken_reason": i.broken_reason,
                "error": i.error,
                "applied": i.applied,
                "plex_updated_at": i.plex_updated_at,
            }
            for i in job.items
        ],
    }


def _deserialize_job(d: dict) -> ScanJob:
    """Deserialize a dict into a ScanJob."""
    items = []
    for item_d in d.get("items", []):
        items.append(
            ScanItem(
                rating_key=item_d["rating_key"],
                title=item_d["title"],
                year=item_d.get("year"),
                item_type=item_d.get("item_type", ""),
                current_poster_url=item_d.get("current_poster_url"),
                current_poster=_deserialize_candidate(item_d.get("current_poster")),
                best_candidate=_deserialize_candidate(item_d.get("best_candidate")),
                all_candidates=[
                    _deserialize_candidate(c)
                    for c in item_d.get("all_candidates", [])
                    if c is not None
                ],
                action=ItemAction(item_d.get("action", "skip")),
                is_locked=item_d.get("is_locked", False),
                is_uploaded=item_d.get("is_uploaded", False),
                is_likely_broken=item_d.get("is_likely_broken", False),
                broken_reason=item_d.get("broken_reason"),
                error=item_d.get("error"),
                applied=item_d.get("applied", False),
                plex_updated_at=item_d.get("plex_updated_at"),
            )
        )

    started_at = None
    if d.get("started_at"):
        started_at = datetime.fromisoformat(d["started_at"])
    completed_at = None
    if d.get("completed_at"):
        completed_at = datetime.fromisoformat(d["completed_at"])

    job = ScanJob(
        job_id=d["job_id"],
        library_key=d["library_key"],
        library_title=d["library_title"],
        status=ScanStatus(d.get("status", "complete")),
        total_items=d.get("total_items", 0),
        processed_items=d.get("processed_items", 0),
        started_at=started_at,
        completed_at=completed_at,
        error=d.get("error"),
        force_refresh=d.get("force_refresh", False),
    )
    job.items = items
    return job


class TaskManager:
    """Manages background scan/apply jobs."""

    def __init__(self, plex_client: PlexClient, config: Config, ignore_list=None):
        self._plex = plex_client
        self._config = config
        self._ignore_list = ignore_list
        self._jobs: dict[str, ScanJob] = {}
        self._apply_jobs: dict[str, ApplyJob] = {}
        self._lock = threading.Lock()
        self._cache_dir = _get_cache_dir()
        self._load_cached_jobs()

    # ── Cache ─────────────────────────────────────────────

    def _load_cached_jobs(self) -> None:
        """Load completed scan jobs from disk cache on startup."""
        loaded = 0
        for path in sorted(self._cache_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = _deserialize_job(data)
                self._jobs[job.job_id] = job
                loaded += 1
            except Exception as e:
                logger.warning("Failed to load cached job %s: %s", path.name, e)
        if loaded:
            logger.info("Loaded %d cached scan jobs", loaded)

    def _save_job_cache(self, job: ScanJob) -> None:
        """Save a completed scan job to disk."""
        try:
            path = self._cache_dir / f"{job.job_id}.json"
            data = _serialize_job(job)
            path.write_text(json.dumps(data), encoding="utf-8")
            logger.debug("Cached scan job %s", job.job_id)
        except Exception as e:
            logger.warning("Failed to cache scan job %s: %s", job.job_id, e)

    def _delete_job_cache(self, job_id: str) -> None:
        """Remove a cached scan job from disk."""
        path = self._cache_dir / f"{job_id}.json"
        if path.exists():
            path.unlink()

    # ── Scan Jobs ───────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[ScanJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[ScanJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_latest_job(self) -> Optional[ScanJob]:
        with self._lock:
            if not self._jobs:
                return None
            return max(self._jobs.values(), key=lambda j: j.started_at or datetime.min)

    def _find_previous_scan(
        self, library_key: str, exclude_job_id: str
    ) -> Optional[ScanJob]:
        """Find the most recent completed scan for a library."""
        best = None
        for j in self._jobs.values():
            if (
                j.library_key == library_key
                and j.job_id != exclude_job_id
                and j.status == ScanStatus.COMPLETE
                and j.items
            ):
                if best is None or (j.completed_at or datetime.min) > (
                    best.completed_at or datetime.min
                ):
                    best = j
        return best

    def start_scan(
        self,
        library_key: str,
        library_title: str,
        force_refresh: bool = False,
    ) -> str:
        """Start a background scan job. Returns job ID."""
        job_id = str(uuid.uuid4())[:8]
        job = ScanJob(
            job_id=job_id,
            library_key=library_key,
            library_title=library_title,
            force_refresh=force_refresh,
            status=ScanStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_scan, args=(job_id,), daemon=True
        )
        thread.start()

        logger.info("Started scan job %s for library '%s'", job_id, library_title)
        return job_id

    def _run_scan(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        try:
            # Verify Plex is still connected before starting
            if not self._plex.is_connected():
                raise ConnectionError(
                    "Plex server is not connected. Reconnect and try again."
                )

            job.status = ScanStatus.SCANNING
            scanner = LibraryScanner(self._plex, self._config)

            # Find the most recent completed scan for this library
            # to enable diff-based scanning (skip unchanged items).
            previous_results = None
            if not job.force_refresh:
                prev_job = self._find_previous_scan(job.library_key, job.job_id)
                if prev_job:
                    previous_results = {
                        i.rating_key: i for i in prev_job.items
                    }
                    logger.info(
                        "Found previous scan with %d items for diff",
                        len(previous_results),
                    )

            def progress_cb(processed: int, total: int) -> None:
                job.processed_items = processed
                job.total_items = total

            results = scanner.scan_library(
                job.library_key,
                force_refresh=job.force_refresh,
                progress_callback=progress_cb,
                previous_results=previous_results,
            )
            job.total_items = len(results)

            # Filter out ignored items — mark them as SKIP so they still
            # appear in results but don't count as actionable changes.
            if self._ignore_list:
                for item in results:
                    if self._ignore_list.is_ignored(item.rating_key):
                        if item.action == ItemAction.CHANGE:
                            item.action = ItemAction.SKIP

            job.items = results
            job.status = ScanStatus.COMPLETE
            job.completed_at = datetime.now(timezone.utc)
            self._save_job_cache(job)
            logger.info("Scan job %s completed: %d items", job_id, len(results))

        except ConnectionError as e:
            job.status = ScanStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error("Scan job %s lost connection: %s", job_id, e)
        except Exception as e:
            job.status = ScanStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error("Scan job %s failed: %s", job_id, e)

    # ── Apply Jobs ──────────────────────────────────────────

    def get_apply_job(self, apply_id: str) -> Optional[ApplyJob]:
        with self._lock:
            return self._apply_jobs.get(apply_id)

    def start_apply(
        self,
        job_id: str,
        dry_run: bool = True,
        item_keys: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Start a background apply job. Returns apply ID or None if invalid."""
        job = self._jobs.get(job_id)
        if not job or job.status != ScanStatus.COMPLETE:
            return None

        # Figure out which items to apply (exclude already-applied items)
        if item_keys:
            items_to_apply = [
                i for i in job.items
                if i.rating_key in item_keys
                and i.action == ItemAction.CHANGE
                and not i.applied
            ]
        else:
            items_to_apply = [
                i for i in job.items
                if i.action == ItemAction.CHANGE and not i.applied
            ]

        if not items_to_apply:
            return None

        apply_id = str(uuid.uuid4())[:8]
        apply_job = ApplyJob(
            apply_id=apply_id,
            scan_job_id=job_id,
            dry_run=dry_run,
            total_items=len(items_to_apply),
            status=ScanStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._apply_jobs[apply_id] = apply_job

        thread = threading.Thread(
            target=self._run_apply,
            args=(apply_id, items_to_apply, dry_run),
            daemon=True,
        )
        thread.start()

        logger.info(
            "Started apply job %s (%d items, dry_run=%s)",
            apply_id, len(items_to_apply), dry_run,
        )
        return apply_id

    def _run_apply(
        self, apply_id: str, items, dry_run: bool
    ) -> None:
        apply_job = self._apply_jobs.get(apply_id)
        if not apply_job:
            return

        try:
            if not dry_run and not self._plex.is_connected():
                raise ConnectionError(
                    "Plex server is not connected. Reconnect and try again."
                )

            apply_job.status = ScanStatus.SCANNING  # reuse as "in progress"
            applier = PosterApplier(self._plex)

            for i, scan_item in enumerate(items):
                applier.apply_item(scan_item, dry_run=dry_run)

                if dry_run:
                    # In dry run, count items that would be changed
                    if scan_item.action == ItemAction.CHANGE:
                        apply_job.applied_count += 1
                else:
                    if scan_item.applied:
                        apply_job.applied_count += 1
                    elif scan_item.action == ItemAction.FAILED:
                        apply_job.failed_count += 1

                apply_job.processed_items = i + 1

            apply_job.status = ScanStatus.COMPLETE
            apply_job.completed_at = datetime.now(timezone.utc)

            # Re-save the parent scan job so applied status persists
            scan_job = self._jobs.get(apply_job.scan_job_id)
            if scan_job:
                self._save_job_cache(scan_job)

            logger.info(
                "Apply job %s completed: %d applied, %d failed",
                apply_id, apply_job.applied_count, apply_job.failed_count,
            )

        except Exception as e:
            apply_job.status = ScanStatus.FAILED
            apply_job.error = str(e)
            apply_job.completed_at = datetime.now(timezone.utc)
            logger.error("Apply job %s failed: %s", apply_id, e)

    # ── Utilities ───────────────────────────────────────────

    def delete_job(self, job_id: str) -> bool:
        """Delete a completed/failed scan job and its cache."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == ScanStatus.SCANNING:
                return False  # can't delete a running job
            del self._jobs[job_id]
        self._delete_job_cache(job_id)
        return True

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.status == ScanStatus.SCANNING:
            job.status = ScanStatus.CANCELLED
            return True
        return False

    def export_job(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        if not job:
            return None

        return {
            "job_id": job.job_id,
            "library": job.library_title,
            "status": job.status.value,
            "total_items": job.total_items,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "summary": {
                "changes": job.changes_count,
                "skipped": job.skipped_count,
                "failed": job.failed_count,
            },
            "items": [
                {
                    "title": i.title,
                    "year": i.year,
                    "action": i.action.value,
                    "current_poster": i.current_poster_url,
                    "best_candidate_provider": (
                        i.best_candidate.provider if i.best_candidate else None
                    ),
                    "best_candidate_score": (
                        i.best_candidate.score if i.best_candidate else None
                    ),
                    "applied": i.applied,
                    "error": i.error,
                }
                for i in job.items
            ],
        }
