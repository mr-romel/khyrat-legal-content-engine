from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from sheets import _append, _ensure_sheet, _execute_with_retry, get_values

QUERY_HEADERS = [
    "Opportunity ID", "Run ID", "Observed At", "Query", "Target URL", "Clicks",
    "Impressions", "CTR", "Average Position", "Intent", "Legal Cluster",
    "Opportunity Type", "Priority Score", "Recommended Action", "Baseline Clicks",
    "Baseline Impressions", "Baseline CTR", "Baseline Position", "Clicks Delta",
    "Impressions Delta", "CTR Delta", "Position Delta", "Measurement Window",
    "Evidence Source", "Status",
]
RUN_HEADERS = [
    "Run ID", "Observed At", "Property", "Window Start", "Window End",
    "Current Query Rows", "Current Page Rows", "Previous Query Rows",
    "Previous Page Rows", "Clicks", "Impressions", "CTR", "Query Opportunities",
    "Indexed URLs", "Not Indexed URLs", "Unknown Inspection URLs", "Data Status",
    "Notes",
]

CLUSTERS = [
    (r"عمل|موظف|عامل|فصل|مرتب|أجر|إجاز|استقال|جزاء", "قانون العمل"),
    (r"عقد|اتفاق|بند|شرط|فسخ|تعاقد", "العقود والالتزامات"),
    (r"شركة|شريك|تأسيس|مدير|جمعية|حصة", "قانون الشركات"),
    (r"شيك|إيصال|دين|مديون|تعويض|مطالبة", "المدني والتجاري"),
    (r"طلاق|نفقة|حضانة|زواج|أسرة", "الأحوال الشخصية"),
    (r"جنائي|حبس|بلاغ|محضر|جريمة|اتهام", "القانون الجنائي"),
    (r"ميراث|تركة|وصية|ورثة", "الميراث والتركات"),
    (r"إيجار|مالك|مستأجر|طرد", "الإيجارات"),
]

def _cluster(query: str) -> str:
    for pattern, name in CLUSTERS:
        if re.search(pattern, query or "", re.I):
            return name
    return "قانوني عام"

def _intent(query: str) -> str:
    q = (query or "").casefold()
    if any(x in q for x in ("ازاي", "إزاي", "كيف", "ماذا أفعل", "أعمل إيه", "اعمل ايه")):
        return "HOW_TO"
    if any(x in q for x in ("هل", "ما هو", "ما هي", "متى", "لماذا", "يجوز", "يحق")):
        return "QUESTION"
    if any(x in q for x in ("محامي", "استشارة", "تكلفة", "سعر", "صياغة", "مراجعة")):
        return "COMMERCIAL"
    return "INFORMATIONAL"

def _score(row: dict[str, Any]) -> float:
    impressions = float(row.get("impressions", 0) or 0)
    clicks = float(row.get("clicks", 0) or 0)
    ctr = float(row.get("ctr", 0) or 0)
    position = float(row.get("position", 0) or 0)
    demand = min(impressions / 500, 1) * 35
    ctr_gap = (max(0, min(1, 0.06 - ctr)) / 0.06) * 30 if impressions >= 20 else 0
    striking = 25 if 4 <= position <= 20 else 12 if 20 < position <= 30 else 0
    click_signal = min(clicks / 50, 1) * 10
    return round(min(100, demand + ctr_gap + striking + click_signal), 2)

def _action(row: dict[str, Any]) -> str:
    impressions = float(row.get("impressions", 0) or 0)
    ctr = float(row.get("ctr", 0) or 0)
    position = float(row.get("position", 0) or 0)
    if impressions >= 50 and 4 <= position <= 20:
        return "REFRESH_EXISTING_PAGE"
    if impressions >= 100 and ctr < 0.02:
        return "IMPROVE_TITLE_AND_SNIPPET"
    if impressions >= 30 and position > 20:
        return "BUILD_SUPPORTING_CONTENT"
    return "MONITOR"

def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(r.get(key, "")): r for r in rows if r.get(key)}

def build_query_ledger_rows(snapshot: dict[str, Any]) -> list[list[str]]:
    current = snapshot.get("query_metrics", [])
    previous = _index(snapshot.get("previous_query_metrics", []), "query_page_key")
    stamp = snapshot.get("generated_at", datetime.now().astimezone().isoformat())
    run_id = hashlib.sha256(
        f'{snapshot.get("site","")}|{snapshot.get("period",{}).get("start","")}|{snapshot.get("period",{}).get("end","")}'.encode()
    ).hexdigest()[:16]
    rows = []
    for item in current:
        if float(item.get("impressions", 0) or 0) < 1:
            continue
        query = str(item.get("query", "")).strip()
        page = str(item.get("page", "")).strip()
        if not query:
            continue
        action = _action(item)
        score = _score(item)
        if action == "MONITOR" and score < 35:
            continue
        old = previous.get(f"{query}||{page}", {})
        delta_clicks = float(item.get("clicks", 0) or 0) - float(old.get("clicks", 0) or 0)
        delta_impressions = float(item.get("impressions", 0) or 0) - float(old.get("impressions", 0) or 0)
        delta_ctr = float(item.get("ctr", 0) or 0) - float(old.get("ctr", 0) or 0)
        delta_position = float(old.get("position", 0) or 0) - float(item.get("position", 0) or 0)
        opportunity_type = (
            "LOW_CTR" if action == "IMPROVE_TITLE_AND_SNIPPET" else
            "STRIKING_DISTANCE" if action == "REFRESH_EXISTING_PAGE" else
            "CONTENT_GAP" if action == "BUILD_SUPPORTING_CONTENT" else "WATCHLIST"
        )
        oid = hashlib.sha256(f"{run_id}|{query}|{page}".encode()).hexdigest()[:20]
        rows.append([
            oid, run_id, stamp, query, page,
            str(item.get("clicks", 0)), str(item.get("impressions", 0)),
            str(item.get("ctr", 0)), str(item.get("position", 0)),
            _intent(query), _cluster(query), opportunity_type, str(score), action,
            str(old.get("clicks", 0)), str(old.get("impressions", 0)),
            str(old.get("ctr", 0)), str(old.get("position", 0)),
            str(round(delta_clicks, 2)), str(round(delta_impressions, 2)),
            str(round(delta_ctr, 5)), str(round(delta_position, 2)),
            f'{snapshot.get("period",{}).get("start","")}..{snapshot.get("period",{}).get("end","")}',
            "Google Search Console API", "OPEN",
        ])
    rows.sort(key=lambda row: float(row[12]), reverse=True)
    return rows[:500]

def write_growth_ledger(snapshot: dict[str, Any], service, spreadsheet_id: str) -> dict[str, int]:
    _ensure_sheet(service, spreadsheet_id, "SEOOpportunityLog", QUERY_HEADERS)
    _ensure_sheet(service, spreadsheet_id, "SEOGrowthRuns", RUN_HEADERS)
    run_id = hashlib.sha256(
        f'{snapshot.get("site","")}|{snapshot.get("period",{}).get("start","")}|{snapshot.get("period",{}).get("end","")}'.encode()
    ).hexdigest()[:16]
    existing_runs = get_values(service, spreadsheet_id, "SEOGrowthRuns!A:A")
    already = {str(row[0]) for row in existing_runs[1:] if row}
    run_written = 0
    if run_id not in already:
        m = snapshot.get("measurement", {})
        idx = snapshot.get("url_inspection", {})
        comparison = snapshot.get("comparison", {})
        _append(service, spreadsheet_id, "SEOGrowthRuns", [
            run_id, snapshot.get("generated_at", ""), snapshot.get("site", ""),
            snapshot.get("period", {}).get("start", ""), snapshot.get("period", {}).get("end", ""),
            str(m.get("queries_with_data", 0)), str(m.get("pages_with_data", 0)),
            str(comparison.get("previous_query_rows", 0)), str(comparison.get("previous_page_rows", 0)),
            str(m.get("clicks", 0)), str(m.get("impressions", 0)), str(m.get("ctr", 0)),
            str(m.get("query_opportunities", 0)), str(idx.get("indexed_pass", 0)),
            str(idx.get("not_indexed_or_blocked", 0)), str(idx.get("unknown_or_api_error", 0)),
            "DATA_AVAILABLE" if m.get("queries_with_data") or m.get("pages_with_data") else "EMPTY_SOURCE",
            "Empty data is not interpreted as zero traffic; verify property access and data freshness.",
        ])
        run_written = 1
    existing_ids = get_values(service, spreadsheet_id, "SEOOpportunityLog!A:A")
    seen = {str(row[0]) for row in existing_ids[1:] if row}
    pending = [row for row in build_query_ledger_rows(snapshot) if row[0] not in seen]
    if pending:
        _execute_with_retry(
            lambda: service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id, range="SEOOpportunityLog!A:Y",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": pending},
            ),
            "writing SEO opportunity ledger",
        )
    return {"run_records_written": run_written, "opportunity_records_written": len(pending)}
