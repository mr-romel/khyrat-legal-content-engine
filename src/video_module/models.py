from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VideoStatus(str, Enum):
    ELIGIBLE = "VIDEO_ELIGIBLE"
    RESERVED = "VIDEO_RESERVED"
    SCRIPT_READY = "SCRIPT_READY"
    AUDIO_READY = "AUDIO_READY"
    RENDERED = "VIDEO_RENDERED"
    VALIDATED = "VALIDATED"
    READY = "READY_FOR_REEL"
    PUBLISHED = "VIDEO_PUBLISHED"
    FAILED = "VIDEO_FAILED"
    QUEUED = "VIDEO_QUEUED"


@dataclass(frozen=True)
class PublishedPost:
    post_id: str
    topic: str
    content: str
    published_at: datetime | None = None


@dataclass
class VideoTask:
    task_id: str
    post_id: str
    status: VideoStatus = VideoStatus.ELIGIBLE
    attempts: int = 0
    reservation_date: str | None = None
    script_path: str | None = None
    audio_path: str | None = None
    video_path: str | None = None
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
