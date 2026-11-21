from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import re
import time

LOG_SHEET = "Recovery Log"
LOG_HEADERS = [
    "Timestamp Cairo", "Row Number", "Row ID", "Topic", "Event",
    "Failure Class", "Strategy", "Attempt", "Outcome", "Reason",
    "Duration Seconds", "Next Action",
]

def classify_failure(error: str, row: dict[str, Any] | None = None) -> tuple[str, str, str]:
    """Map a failure signature to a recovery lane, strategy and operator action."""
    value = str(error or "").casefold()
    row = row or {}
    if any(x in value for x in ("http 401", "401 unauthorized", "token has expired", "userinfo failed", "blocked_token")):
        return "AUTHORIZATION", "HOLD_AND_ALERT", "Renew the affected platform credential; do not retry-loop."
    if any(x in value for x in ("legal_citation_gate", "mandatory_legal_review", "no retrieved primary", "legal_source")):
        return "LEGAL_EVIDENCE", "REFRESH_PRIMARY_SOURCES", "Refresh primary/official legal sources; publication gate remains closed."
    if any(x in value for x in ("image_qa", "semantic qa", "visual relevance", "image_required_blocked", "image_provider")):
        return "VISUAL_ASSET", "REBUILD_BRIEF_AND_ROTATE_PROVIDER", "Regenerate a topic-specific visual and run semantic QA again."
    if any(x in value for x in ("429", "quota", "rate limit", "resource_exhausted", "503", "502", "timeout")):
        return "TRANSIENT_PROVIDER", "SWITCH_PROVIDER_AND_BACKOFF", "Use an alternate configured provider, then bounded backoff."
    if any(x in value for x in ("google sheets", "spreadsheet", "service unavailable", "connection reset")):
        return "PERSISTENCE", "RETRY_PERSISTENCE_ONLY", "Retry state persistence without repeating external publication."
    if any(x in value for x in ("editorial", "review", "linkedin copy")):
        return "EDITORIAL", "REBUILD_EDITORIAL_PACKAGE", "Rebuild editorial assets; do not bypass legal review."
    return "UNKNOWN", "CLEAN_RESTART_BOUNDED", "Retry once in a later fair queue cycle; escalate after repeated identical failures."

def next_retry_at(now: datetime, failure_class: str, attempt: int) -> datetime | None:
    if failure_class == "AUTHORIZATION":
        return None
    if failure_class == "LEGAL_EVIDENCE":
        minutes = min(24 * 60, 60 * max(1, attempt))
    elif failure_class == "VISUAL_ASSET":
        minutes = min(6 * 60, 20 * max(1, attempt))
    elif failure_class == "TRANSIENT_PROVIDER":
        minutes = min(90, 5 * (2 ** min(max(0, attempt - 1), 4)))
    elif failure_class == "PERSISTENCE":
        minutes = min(60, 3 * (2 ** min(max(0, attempt - 1), 4)))
    else:
        minutes = min(180, 15 * max(1, attempt))
    return now + timedelta(minutes=minutes)

def _ensure_log_sheet(service, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    if any(str(s.get("properties", {}).get("title", "")).casefold() == LOG_SHEET.casefold()
           for s in metadata.get("sheets", [])):
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": LOG_SHEET}}}]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f"'{LOG_SHEET}'!A1:L1",
        valueInputOption="RAW", body={"values": [LOG_HEADERS]},
    ).execute()

def log_event(service, spreadsheet_id: str, *, timestamp: str, row_number: int,
              row: dict[str, Any], event: str, failure_class: str = "",
              strategy: str = "", attempt: int = 0, outcome: str = "",
              reason: str = "", duration: float = 0, next_action: str = "") -> None:
    """Append-only audit record. Logging failure is non-fatal to publishing."""
    try:
        _ensure_log_sheet(service, spreadsheet_id)
        values = [[timestamp, row_number, row.get("ID", ""), row.get("الموضوع", ""),
                   event, failure_class, strategy, attempt, outcome,
                   str(reason or "")[:2500], round(float(duration or 0), 2), next_action]]
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=f"'{LOG_SHEET}'!A:L",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
    except Exception as exc:
        print(f"RECOVERY_LOG_WRITE_FAILED: {type(exc).__name__}: {exc}")

def is_stale_processing(row: dict[str, Any], now: datetime, stale_minutes: int = 35) -> bool:
    if str(row.get("الحالة", "")).strip().upper() != "PROCESSING":
        return False
    raw = str(row.get("وقت آخر تشغيل", "") or "").strip()
    if not raw:
        return True
    try:
        started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        current = now
        if started.tzinfo and not current.tzinfo:
            current = current.replace(tzinfo=started.tzinfo)
        elif current.tzinfo and not started.tzinfo:
            started = started.replace(tzinfo=current.tzinfo)
        return (current - started).total_seconds() >= stale_minutes * 60
    except (TypeError, ValueError):
        return True

def retry_is_due(row: dict[str, Any], now: datetime) -> bool:
    raw = str(row.get("Recovery Next At", "") or "").strip()
    if not raw:
        return True
    try:
        due = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        current = now
        if due.tzinfo and not current.tzinfo:
            current = current.replace(tzinfo=due.tzinfo)
        elif current.tzinfo and not due.tzinfo:
            due = due.replace(tzinfo=current.tzinfo)
        return current >= due
    except (TypeError, ValueError):
        return True

def choose_fair_candidate(candidates: list[tuple[int, dict[str, Any]]]) -> tuple[int, dict[str, Any]] | None:
    """Oldest attempted row wins; blank timestamps naturally get first service."""
    if not candidates:
        return None
    def key(item):
        row = item[1]
        return (str(row.get("وقت آخر تشغيل", "") or ""), item[0])
    return sorted(candidates, key=key)[0]
