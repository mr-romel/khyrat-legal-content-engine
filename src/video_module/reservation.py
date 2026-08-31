from __future__ import annotations

from datetime import date

from .models import VideoStatus, VideoTask


class ReservationStore:
    """Minimal in-memory reservation store; persistence is deliberately deferred."""

    def __init__(self) -> None:
        self._tasks: dict[str, VideoTask] = {}

    def reserve(self, task: VideoTask, day: date) -> VideoTask | None:
        existing = self._tasks.get(task.task_id)
        if existing is not None:
            return None
        task.status = VideoStatus.RESERVED
        task.reservation_date = day.isoformat()
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> VideoTask | None:
        return self._tasks.get(task_id)

    def used_post_ids(self) -> set[str]:
        return {task.post_id for task in self._tasks.values()}
