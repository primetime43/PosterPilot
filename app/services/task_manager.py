"""Background task manager for long-running scan and apply operations.

Uses threading to run scans and applies in the background while
providing progress updates via polling.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import Config
from app.models import ApplyJob, ItemAction, ScanJob, ScanStatus
from app.services.library_scanner import LibraryScanner
from app.services.plex_client import PlexClient
from app.services.poster_applier import PosterApplier

logger = logging.getLogger("posterpilot.task_manager")


class TaskManager:
    """Manages background scan/apply jobs."""

    def __init__(self, plex_client: PlexClient, config: Config):
        self._plex = plex_client
        self._config = config
        self._jobs: dict[str, ScanJob] = {}
        self._apply_jobs: dict[str, ApplyJob] = {}
        self._lock = threading.Lock()

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
            job.status = ScanStatus.SCANNING
            scanner = LibraryScanner(self._plex, self._config)

            items = self._plex.get_library_items(job.library_key)
            job.total_items = len(items)

            def progress_cb(processed: int, total: int) -> None:
                job.processed_items = processed

            results = scanner.scan_library(
                job.library_key,
                force_refresh=job.force_refresh,
                progress_callback=progress_cb,
            )

            job.items = results
            job.status = ScanStatus.COMPLETE
            job.completed_at = datetime.now(timezone.utc)
            logger.info("Scan job %s completed: %d items", job_id, len(results))

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

        # Figure out which items to apply
        if item_keys:
            items_to_apply = [
                i for i in job.items
                if i.rating_key in item_keys and i.action == ItemAction.CHANGE
            ]
        else:
            items_to_apply = [i for i in job.items if i.action == ItemAction.CHANGE]

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
            apply_job.status = ScanStatus.SCANNING  # reuse as "in progress"
            applier = PosterApplier(self._plex)

            for i, scan_item in enumerate(items):
                applier.apply_item(scan_item, dry_run=dry_run)

                if scan_item.applied:
                    apply_job.applied_count += 1
                elif scan_item.action == ItemAction.FAILED:
                    apply_job.failed_count += 1

                apply_job.processed_items = i + 1

            apply_job.status = ScanStatus.COMPLETE
            apply_job.completed_at = datetime.now(timezone.utc)
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
