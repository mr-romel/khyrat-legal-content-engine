from __future__ import annotations

import ast
from pathlib import Path

from src.video_module.models import PublishedPost, VideoStatus
from src.video_module.queue import MAX_REELS_PER_DAY, reserve_daily_task
from src.video_module.reservation import ReservationStore
from src.video_module.selector import first_eligible_post, make_task


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "src" / "video_module"


def test_video_module_has_no_core_imports() -> None:
    forbidden = {
        "analytics", "comment_engine", "config", "facebook_publisher", "gemini",
        "gemini_chat", "linkedin_publisher", "main", "monthly_recycler", "sheets",
        "telegram_bot", "utils",
    }
    for path in VIDEO_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] not in forbidden for alias in node.names), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, path


def test_selector_skips_used_posts() -> None:
    posts = [
        PublishedPost("p1", "one", "content"),
        PublishedPost("p2", "two", "content"),
    ]
    selected = first_eligible_post(posts, {"p1"})
    assert selected is not None
    assert selected.post_id == "p2"


def test_reservation_prevents_duplicate_task() -> None:
    from datetime import date

    store = ReservationStore()
    task = make_task(PublishedPost("p1", "one", "content"))
    assert store.reserve(task, date(2026, 8, 31)) is task
    duplicate = make_task(PublishedPost("p1", "one", "content"))
    assert store.reserve(duplicate, date(2026, 8, 31)) is None
    assert task.status == VideoStatus.RESERVED


def test_daily_budget_is_one() -> None:
    from datetime import date

    store = ReservationStore()
    day = date(2026, 8, 31)
    tasks = [
        make_task(PublishedPost("p1", "one", "content")),
        make_task(PublishedPost("p2", "two", "content")),
    ]
    assert MAX_REELS_PER_DAY == 1
    assert reserve_daily_task(tasks, store, day) is tasks[0]
    assert reserve_daily_task(tasks, store, day) is None
