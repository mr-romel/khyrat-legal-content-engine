from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import quote

import requests

from sheets import get_values
from telegram_bot import notify

SHEET = "Performance"
HEADERS = [
    "Checked At",
    "Topic",
    "Facebook Post ID",
    "Facebook Comments",
    "Facebook Reactions",
    "Facebook Shares",
    "LinkedIn Post ID",
    "LinkedIn Comments",
    "LinkedIn Likes",
    "Status",
]


def ensure_sheet(service, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    titles = {str(s.get("properties", {}).get("title", "")).strip().casefold() for s in metadata.get("sheets", [])}
    if SHEET.casefold() not in titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SHEET}}}]},
        ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET}!A1:J1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def _count_summary(value: dict, key: str) -> int:
    summary = value.get(key, {}) if isinstance(value, dict) else {}
    return int(summary.get("total_count", summary.get("total", 0)) or 0)


def collect(*, service, spreadsheet_id: str, page_access_token: str, graph_version: str, linkedin_access_token: str) -> None:
    ensure_sheet(service, spreadsheet_id)
    postbank = get_values(service, spreadsheet_id, "PostBank!A:N")
    if len(postbank) <= 1:
        return

    rows = []
    for raw in postbank[1:]:
        padded = list(raw) + [""] * (14 - len(raw))
        rows.append({
            "topic": padded[1],
            "facebook": padded[5],
            "linkedin": padded[6],
        })

    now = datetime.now().astimezone().isoformat()
    output = []
    for row in rows[-20:]:
        fb_comments = fb_reactions = fb_shares = 0
        li_comments = li_likes = 0
        status = "OK"

        if row["facebook"]:
            try:
                response = requests.get(
                    f"https://graph.facebook.com/v{graph_version}/{row['facebook']}",
                    params={
                        "fields": "comments.limit(0).summary(true),reactions.limit(0).summary(true),shares",
                        "access_token": page_access_token,
                    },
                    timeout=30,
                )
                if response.ok:
                    data = response.json()
                    fb_comments = _count_summary(data.get("comments", {}), "summary")
                    fb_reactions = _count_summary(data.get("reactions", {}), "summary")
                    fb_shares = int(data.get("shares", {}).get("count", 0) or 0)
                else:
                    status = "FACEBOOK_METRICS_FAILED"
            except Exception:
                status = "FACEBOOK_METRICS_FAILED"

        if row["linkedin"]:
            try:
                encoded = quote(row["linkedin"], safe="")
                response = requests.get(
                    f"https://api.linkedin.com/rest/socialActions/{encoded}",
                    headers={
                        "Authorization": f"Bearer {linkedin_access_token}",
                        "Linkedin-Version": "202607",
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    timeout=30,
                )
                if response.ok:
                    data = response.json()
                    li_comments = int(data.get("commentsSummary", {}).get("totalFirstLevelComments", 0) or 0)
                    li_likes = int(data.get("likesSummary", {}).get("totalLikes", 0) or 0)
                else:
                    status = "LINKEDIN_METRICS_FAILED"
            except Exception:
                status = "LINKEDIN_METRICS_FAILED"

        output.append([
            now,
            row["topic"],
            row["facebook"],
            fb_comments,
            fb_reactions,
            fb_shares,
            row["linkedin"],
            li_comments,
            li_likes,
            status,
        ])

    if output:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{SHEET}!A:J",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": output},
        ).execute()
        notify(f"📈 Performance collector completed for {len(output)} recent posts.")
