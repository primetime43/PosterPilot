"""Data models for PosterPilot."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ScanStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ItemAction(str, Enum):
    CHANGE = "change"
    SKIP = "skip"
    NO_ALTERNATIVES = "no_alternatives"
    FAILED = "failed"
    LOCKED = "locked"


@dataclass
class PosterCandidate:
    """A single poster option for a media item."""

    rating_key: str
    thumb_url: str
    provider: Optional[str] = None
    selected: bool = False
    score: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    score_breakdown: dict = field(default_factory=dict)


@dataclass
class ScanItem:
    """Result of scanning a single media item."""

    rating_key: str
    title: str
    year: Optional[int] = None
    item_type: str = ""
    current_poster_url: Optional[str] = None
    current_poster: Optional[PosterCandidate] = None
    best_candidate: Optional[PosterCandidate] = None
    all_candidates: list[PosterCandidate] = field(default_factory=list)
    action: ItemAction = ItemAction.SKIP
    is_locked: bool = False
    error: Optional[str] = None
    applied: bool = False


@dataclass
class ScanJob:
    """A background scan job."""

    job_id: str
    library_key: str
    library_title: str
    status: ScanStatus = ScanStatus.PENDING
    total_items: int = 0
    processed_items: int = 0
    items: list[ScanItem] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    force_refresh: bool = False

    @property
    def progress_pct(self) -> int:
        if self.total_items == 0:
            return 0
        return int((self.processed_items / self.total_items) * 100)

    @property
    def changes_count(self) -> int:
        return sum(1 for i in self.items if i.action == ItemAction.CHANGE)

    @property
    def skipped_count(self) -> int:
        return sum(1 for i in self.items if i.action == ItemAction.SKIP)

    @property
    def failed_count(self) -> int:
        return sum(1 for i in self.items if i.action == ItemAction.FAILED)

    @property
    def locked_count(self) -> int:
        return sum(1 for i in self.items if i.action == ItemAction.LOCKED)


@dataclass
class ApplyJob:
    """A background apply job."""

    apply_id: str
    scan_job_id: str
    status: ScanStatus = ScanStatus.PENDING
    dry_run: bool = False
    total_items: int = 0
    processed_items: int = 0
    applied_count: int = 0
    failed_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def progress_pct(self) -> int:
        if self.total_items == 0:
            return 0
        return int((self.processed_items / self.total_items) * 100)


@dataclass
class LibraryInfo:
    """Plex library metadata."""

    key: str
    title: str
    type: str
    item_count: int = 0


@dataclass
class PlexConnectionStatus:
    """Status of the Plex connection."""

    connected: bool = False
    server_name: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None
