from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

from content_system import (
    SYSTEM_SHEETS,
    _append,
    _now,
    content_fingerprint,
    infer_audience_persona,
    choose_visual_concept,
)
from sheets import get_values


def _rows(service, spreadsheet_id: str, sheet: str, headers: list[str]) -> list[dict[str, str]]:
    values = get_values(service, spreadsheet_id, f"{sheet}!A:Z")
    if len(values) <= 1:
        return []
    rows = []
    for raw in values[1:]:
        padded = list(raw) + [""] * (len(headers) - len(raw))
        rows.append({headers[i]: str(padded[i]) for i in range(len(headers))})
    return rows


def _num(row: dict[str, str], key: str) -> float:
    try:
        return float(str(row.get(key, "0") or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _top(rows: list[dict[str, str]], key: str, n: int = 5) -> list[tuple[str, float]]:
    counts = Counter(str(row.get(key, "")).strip() for row in rows if str(row.get(key, "")).strip())
    return counts.most_common(n)


def build_strategy(service, spreadsheet_id: str) -> dict[str, object]:
    metrics = _rows(service, spreadsheet_id, "ContentMetrics", SYSTEM_SHEETS["ContentMetrics"])
    fingerprints = _rows(service, spreadsheet_id, "ContentFingerprints", SYSTEM_SHEETS["ContentFingerprints"])
    performance = _rows(service, spreadsheet_id, "Performance", [
        "Checked At", "Topic", "Facebook Post ID", "Facebook Comments", "Facebook Reactions",
        "Facebook Shares", "LinkedIn Post ID", "LinkedIn Comments", "LinkedIn Likes", "Status",
    ])

    by_platform: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in metrics:
        by_platform[str(row.get("Platform", "UNKNOWN")).upper()].append(row)

    recommendations = []
    rid = 0

    def add(priority, platform, audience, pillar, angle, action, evidence):
        nonlocal rid
        rid += 1
        recommendations.append([
            f"REC-{datetime.now().strftime('%Y%m%d')}-{rid:03d}",
            priority, platform, audience, pillar, angle, action, evidence, _now(),
        ])

    # Data-backed signals when enough observations exist; otherwise give
    # operational recommendations that can be measured in the next cycle.
    for platform, rows in by_platform.items():
        if not rows:
            continue
        top_topics = _top(rows, "Topic", 3)
        top_reactions = sorted(rows, key=lambda r: _num(r, "Reactions"), reverse=True)[:3]
        top_comments = sorted(rows, key=lambda r: _num(r, "Comments"), reverse=True)[:3]
        if top_comments:
            add("HIGH", platform, "صاحب قرار مهني", "أعلى تفاعل",
                "الأسئلة والمواقف العملية", "اختبر Hook سؤال أو موقف واقعي على الموضوعات التي سجلت أعلى تعليقات",
                json.dumps({"top_comments": [r.get("Topic", "") for r in top_comments]}, ensure_ascii=False))
        if top_reactions:
            add("MEDIUM", platform, "الجمهور العام", "أعلى توزيع",
                "المعلومة المباشرة", "اختبر افتتاحية مباشرة قصيرة قبل الشرح القانوني",
                json.dumps({"top_reactions": [r.get("Topic", "") for r in top_reactions]}, ensure_ascii=False))
        if top_topics:
            add("MEDIUM", platform, "الجمهور الأساسي", "التغطية",
                "زاوية جديدة", "استخرج Follow-up من أفضل الموضوعات بدل إعادة المنشور نفسه",
                json.dumps({"top_topics": top_topics}, ensure_ascii=False))

    # Always maintain explicit persona rows so the generator can consume them.
    persona_rows = [
        ["صاحب شركة", "FACEBOOK", "حل المشكلة قبل تحولها إلى نزاع", "شركة، عقد، مدير، شريك", "خطأ شائع أو موقف واقعي", "مشاركة أو سؤال عام", _now()],
        ["صاحب شركة / مدير", "LINKEDIN", "تقليل المخاطر واتخاذ قرار عملي", "شركة، قرار، تعاقد، مسؤولية", "Insight مباشر أو سؤال من الواقع", "تعليق أو نقاش مهني", _now()],
        ["HR / مدير موارد بشرية", "LINKEDIN", "إدارة موقف قانوني قبل تصعيده", "موظف، فصل، استقالة، جزاء", "موقف إداري محدد", "سؤال عملي", _now()],
        ["الجمهور العام", "FACEBOOK", "فهم القاعدة القانونية وتطبيقها", "حق، إجراء، موعد، نزاع", "تحذير أو Myth/Fact", "مشاركة", _now()],
    ]

    for row in persona_rows:
        _append(service, spreadsheet_id, "AudiencePersonas", row)

    for row in recommendations:
        _append(service, spreadsheet_id, "StrategyRecommendations", row)

    return {
        "metrics_count": len(metrics),
        "fingerprints_count": len(fingerprints),
        "performance_count": len(performance),
        "recommendations": recommendations,
        "personas": persona_rows,
    }


def build_dashboard_html(snapshot: dict[str, object], output_path: str = "reports/content-intelligence.html") -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    recommendations = snapshot.get("recommendations", [])
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in recommendations
    )
    html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Khyrat Content Intelligence</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1200px;margin:40px auto;padding:0 20px;background:#f7f7f7;color:#222}}
.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px 0}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:right;vertical-align:top}}
h1{{margin-bottom:6px}}small{{color:#666}}
</style>
</head>
<body>
<h1>Khyrat Content Intelligence</h1>
<small>Snapshot: {escape(_now())}</small>
<div class="card"><strong>Metrics</strong><p>{snapshot.get("metrics_count", 0)} metric rows | {snapshot.get("fingerprints_count", 0)} fingerprints | {snapshot.get("performance_count", 0)} performance rows</p></div>
<div class="card"><h2>Strategy Recommendations</h2>
<table><thead><tr><th>ID</th><th>Priority</th><th>Platform</th><th>Audience</th><th>Pillar</th><th>Angle</th><th>Action</th><th>Evidence</th><th>Updated</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</body>
</html>"""
    Path(output_path).write_text(html, encoding="utf-8")
    return output_path
