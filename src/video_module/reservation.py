from __future__ import annotations

from datetime import date

from .models import VideoStatus, VideoTask


class ReservationStore:
    """Isolated reservation ledger; no Google Sheet writes."""

    def __init__(self) -> None:
        self._tasks: dict[str, VideoTask] = {}

    def reserve(self, task: VideoTask, day: date) -> VideoTask | None:
        if task.task_id in self._tasks:
            return None
        task.status = VideoStatus.RESERVED
        task.reservation_date = day.isoformat()
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> VideoTask | None:
        return self._tasks.get(task_id)

    def used_post_ids(self) -> set[str]:
        return {task.post_id for task in self._tasks.values()}

    def reserve_first(self, posts, day: date) -> VideoTask | None:
        used = self.used_post_ids()
        for post in posts:
            if post.post_id in used:
                continue
            task = VideoTask(task_id=f"video:{post.post_id}", post_id=post.post_id)
            return self.reserve(task, day)
        return None
