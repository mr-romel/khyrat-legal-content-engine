from __future__ import annotations

from .models import PublishedPost, VideoTask


def first_eligible_post(posts: list[PublishedPost], used_post_ids: set[str]) -> PublishedPost | None:
    """Return the first published post not previously used for video."""
    for post in posts:
        if post.post_id and post.post_id not in used_post_ids:
            return post
    return None


def make_task(post: PublishedPost) -> VideoTask:
    """Create a deterministic task identity from the source post ID."""
    return VideoTask(task_id=f"reel-{post.post_id}", post_id=post.post_id)
