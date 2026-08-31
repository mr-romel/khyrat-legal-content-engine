from __future__ import annotations

from datetime import date

from .models import VideoStatus, VideoTask
from .reservation import ReservationStore

MAX_REELS_PER_DAY = 1


def reserve_daily_task(tasks: list[VideoTask], store: ReservationStore, day: date) -> VideoTask | None:
    """Reserve at most one Reel per Cairo calendar day."""
    reserved_today = sum(
        1 for task in tasks
        if task.reservation_date == day.isoformat()
        and task.status in {
            VideoStatus.RESERVED,
            VideoStatus.SCRIPT_READY,
            VideoStatus.AUDIO_READY,
            VideoStatus.RENDERED,
            VideoStatus.VALIDATED,
            VideoStatus.READY,
            VideoStatus.QUEUED,
            VideoStatus.PUBLISHED,
        }
    )
    if reserved_today >= MAX_REELS_PER_DAY:
        return None

    for task in tasks:
        if task.status != VideoStatus.ELIGIBLE:
            continue
        reserved = store.reserve(task, day)
        if reserved is not None:
            return reserved
    return None
