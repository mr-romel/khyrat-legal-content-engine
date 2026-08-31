"""Read-only Google Sheets adapter for the isolated Video Module."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


@dataclass(frozen=True)
class SheetPost:
    row_number: int
    post_id: str
    topic: str
    content: str
    status: str
    published_at: str
    image_url: str
    facebook_status: str = ""
    linkedin_status: str = ""
    facebook_post_id: str = ""
    linkedin_post_id: str = ""


def _service() -> Any:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not raw or not sheet_id:
        raise RuntimeError("Video Module requires GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID")
    credentials = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def read_rows(sheet_range: str | None = None) -> list[list[str]]:
    target = sheet_range or os.environ.get("GOOGLE_SHEET_RANGE", "Content!A:U")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is required")
    response = _service().spreadsheets().values().get(spreadsheetId=sheet_id, range=target).execute()
    return response.get("values", [])


def posts_from_rows(rows: list[list[str]]) -> list[SheetPost]:
    if not rows:
        return []
    header = {str(value).strip().lower(): index for index, value in enumerate(rows[0])}

    def get(row: list[str], *names: str) -> str:
        for name in names:
            index = header.get(name.lower())
            if index is not None and index < len(row):
                return str(row[index]).strip()
        return ""

    posts: list[SheetPost] = []
    for number, row in enumerate(rows[1:], start=2):
        post_id = get(row, "post_id", "post id", "facebook post id", "id")
        topic = get(row, "topic", "الموضوع")
        content = get(row, "content", "post", "post_content", "المحتوى", "النص")
        status = get(row, "status", "حالة النشر", "publish_status", "الحالة")
        published_at = get(row, "published_at", "published at", "publish_date", "تاريخ النشر")
        image_url = get(row, "image_url", "image url", "image", "رابط الصورة")
        facebook_status = get(row, "facebook status")
        linkedin_status = get(row, "linkedin status")
        facebook_post_id = get(row, "facebook post id")
        linkedin_post_id = get(row, "linkedin post id")
        if post_id or facebook_post_id:
            posts.append(SheetPost(number, post_id or facebook_post_id, topic, content, status, published_at, image_url, facebook_status, linkedin_status, facebook_post_id, linkedin_post_id))
    return posts


def is_published(post: SheetPost) -> bool:
    published_values = {"PUBLISHED", "PUBLISHED_SUCCESS", "POSTED", "SUCCESS", "تم النشر", "منشور"}
    values = {post.status.strip().upper(), post.facebook_status.strip().upper()}
    return bool(post.facebook_post_id.strip()) or bool(values & published_values)
