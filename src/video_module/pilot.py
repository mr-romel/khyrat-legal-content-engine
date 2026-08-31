from __future__ import annotations

import hashlib
from datetime import date

from .models import VideoTask
from .reservation import ReservationStore
from .sheets_adapter import is_published, posts_from_rows, read_rows
from .script import build_reel_script


def build_first_pilot_task() -> tuple[VideoTask | None, str | None]:
    posts = [p for p in posts_from_rows(read_rows()) if is_published(p)]
    store = ReservationStore()
    if not posts:
        return None, None
    post = posts[0]
    task = store.reserve_first(posts, date.today())
    if task is None:
        return None, None
    script = build_reel_script(post.topic, post.content)
    task.script_path = f"generated/video/{hashlib.sha256(task.post_id.encode()).hexdigest()[:16]}.txt"
    task.metadata["topic"] = post.topic
    task.metadata["image_url"] = post.image_url
    task.metadata["script"] = script
    task.status = task.status.SCRIPT_READY
    return task, script
