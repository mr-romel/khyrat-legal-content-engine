from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    """Classify only explicit HTTP status fields or bounded, recognizable error signatures."""
    value = str(error or "").casefold()
    row = row or {}
    status = row.get("http_status", row.get("status_code", row.get("httpStatus")))
    try:
        status_code = int(status) if status not in (None, "") else None
    except (TypeError, ValueError):
        status_code = None
    if status_code == 401 or re.search(r"\bhttp(?:/\d(?:\.\d)?)?\s*[:=]?\s*401\b|\b401\s+unauthorized\b", value) or any(
        signature in value for signature in ("token has expired", "userinfo failed", "blocked_token")
    ):
        return "AUTHORIZATION", "HOLD_AND_ALERT", "Renew the affected platform credential; do not retry-loop."
    if any(x in value for x in ("legal_citation_gate", "mandatory_legal_review", "no retrieved primary", "legal_source")):
        return "LEGAL_EVIDENCE", "REFRESH_PRIMARY_SOURCES", "Refresh primary/official legal sources; publication gate remains closed."
    if any(x in value for x in ("image_qa", "semantic qa", "visual relevance", "image_required_blocked", "image_provider")):
        return "VISUAL_ASSET", "REBUILD_BRIEF_AND_ROTATE_PROVIDER", "Regenerate a topic-specific visual and run semantic QA again."
    transient_code = status_code in {429, 500, 502, 503, 504}
    transient_signature = bool(re.search(
        r"\bhttp(?:/\d(?:\.\d)?)?\s*[:=]?\s*(?:429|500|502|503|504)\b|"
        r"\b(?:429|500|502|503|504)\s+(?:too many requests|bad gateway|service unavailable|gateway timeout)\b",
        value,
    ))
    if transient_code or transient_signature or any(x in value for x in ("quota exceeded", "rate limit", "resource_exhausted", "timeout")):
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
    exists = any(
        str(sheet.get("properties", {}).get("title", "")).casefold() == LOG_SHEET.casefold()
        for sheet in metadata.get("sheets", [])
    )
    if not exists:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": LOG_SHEET}}}]},
        ).execute()
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"'{LOG_SHEET}'!A1:L1"
    ).execute().get("values", [])
    if not current or current[0][:len(LOG_HEADERS)] != LOG_HEADERS:
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
    if raw.upper() == "HOLD":
        return False
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
    """Oldest valid attempt instant wins; blank timestamps get first service."""
    if not candidates:
        return None
    def key(item):
        raw = str(item[1].get("وقت آخر تشغيل", "") or "").strip()
        if not raw:
            return (0, datetime.min.replace(tzinfo=timezone.utc), item[0])
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (1, parsed.astimezone(timezone.utc), item[0])
        except (TypeError, ValueError):
            return (0, datetime.min.replace(tzinfo=timezone.utc), item[0])
    return min(candidates, key=key)

def refresh_dashboard(service, spreadsheet_id: str, content_range: str) -> None:
    """Refresh a compact live operational dashboard from queue state and audit events."""
    dashboard = "Recovery Dashboard"
    try:
        metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets.properties"
        ).execute()
        exists = any(
            str(sheet.get("properties", {}).get("title", "")).casefold() == dashboard.casefold()
            for sheet in metadata.get("sheets", [])
        )
        if not exists:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": dashboard}}}]},
            ).execute()
        queue_values = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=content_range
        ).execute().get("values", [])
        headers = [str(x or "").strip() for x in (queue_values[0] if queue_values else [])]
        records = []
        for values in queue_values[1:]:
            padded = list(values) + [""] * max(0, len(headers) - len(values))
            records.append({h: str(padded[i] or "") for i, h in enumerate(headers) if h})
        statuses = {}
        failures = {}
        for row in records:
            status = row.get("الحالة", "").strip().upper() or "UNSET"
            statuses[status] = statuses.get(status, 0) + 1
            failure = row.get("Recovery Failure Class", "").strip() or "UNCLASSIFIED"
            if status in {"FAILED", "PARTIAL_FAILED"}:
                failures[failure] = failures.get(failure, 0) + 1
        _ensure_log_sheet(service, spreadsheet_id)
        events = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{LOG_SHEET}'!A:L"
        ).execute().get("values", [])
        outcomes = [str(row[8]).upper() for row in events[1:] if len(row) > 8]
        recovered = sum(1 for value in outcomes if value == "RECOVERED")
        failed_attempts = sum(1 for value in outcomes if value == "FAILED")
        holds = sum(1 for row in records if row.get("Recovery Next At", "").strip().upper() == "HOLD")
        rows = [
            ["Khyrat Legal Content Engine — Recovery Dashboard", "Value", "Updated At"],
            ["Queue rows", len(records), datetime.now().astimezone().isoformat()],
            ["READY", statuses.get("READY", 0), ""],
            ["PROCESSING", statuses.get("PROCESSING", 0), ""],
            ["PUBLISHED", statuses.get("PUBLISHED", 0), ""],
            ["FAILED", statuses.get("FAILED", 0), ""],
            ["PARTIAL_FAILED", statuses.get("PARTIAL_FAILED", 0), ""],
            ["Manual holds", holds, ""],
            ["Recovery attempts logged", sum(1 for row in events[1:] if len(row) > 4 and str(row[4]).upper() == "ATTEMPT_STARTED"), ""],
            ["Recovered attempts", recovered, ""],
            ["Failed attempts", failed_attempts, ""],
            ["Failure classes (active)", " | ".join(f"{k}:{v}" for k, v in sorted(failures.items())), ""],
        ]
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'{dashboard}'!A1:C{len(rows)}",
            valueInputOption="RAW", body={"values": rows},
        ).execute()
    except Exception as exc:
        print(f"RECOVERY_DASHBOARD_REFRESH_FAILED: {type(exc).__name__}: {exc}")
