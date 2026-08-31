"""Read-only Google Sheets adapter for the isolated Video Module.

This module intentionally does not import src.sheets or any Core publisher.
It uses the same Google service-account secret shape but owns its own client.
"""
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


def _service() -> Any:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not raw or not sheet_id:
        raise RuntimeError("Video Module requires GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID")
    info = json.loads(raw)
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
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
            index = header.get(name)
            if index is not None and index < len(row):
                return str(row[index]).strip()
        return ""

    posts: list[SheetPost] = []
    for number, row in enumerate(rows[1:], start=2):
        post_id = get(row, "post_id", "post id", "id")
        topic = get(row, "topic", "الموضوع")
        content = get(row, "content", "post", "post_content", "النص")
        status = get(row, "status", "حالة النشر", "publish_status")
        published_at = get(row, "published_at", "published at", "publish_date", "تاريخ النشر")
        image_url = get(row, "image_url", "image url", "image", "رابط الصورة")
        if post_id and status:
            posts.append(SheetPost(number, post_id, topic, content, status, published_at, image_url))
    return posts
