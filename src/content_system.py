from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from sheets import get_values


SYSTEM_SHEETS = {
    "ContentLineage": ["Lineage ID", "Parent ID", "Source Row ID", "Topic", "Asset Type", "Angle", "Platform", "Objective", "Service", "Experiment ID", "Created At"],
    "AudienceFeedback": ["Feedback ID", "Post ID", "Platform", "Text", "Intent", "Sentiment", "Topic Signal", "Content Opportunity", "Created At"],
    "ContentWinners": ["Post ID", "Topic", "Score", "Tier", "Metrics JSON", "Next Actions", "Updated At"],
    "AuthorityMap": ["Topic Cluster", "Posts", "Winners", "Avg Score", "Coverage", "Status", "Updated At"],
    "ConversionMap": ["Topic Pattern", "Service", "Intent", "CTA", "Lead Signal"],
    "VoiceProfile": ["Version", "Principles", "Preferred Openings", "Forbidden", "Tone", "CTA", "Updated At"],
    "ContentExperiments": ["Experiment ID", "Post ID", "Variable", "Variant", "Hypothesis", "Status", "Created At"],
    "ContentMetrics": ["Post ID", "Topic", "Platform", "Impressions", "Reach", "Reactions", "Comments", "Shares", "Saves", "Clicks", "Leads", "Captured At"],
}

DERIVATIVE_TYPES = [
    "POST", "REEL", "CAROUSEL", "FAQ", "CASE_STUDY", "MYTH_FACT", "CHECKLIST", "WARNING", "COMPARISON", "QUESTION", "FOLLOW_UP", "CTA_ASSET",
]

SERVICE_RULES = [
    (r"عقد|اتفاق|بند|شرط", "مراجعة وصياغة العقود", "HIGH_INTENT", "لو عندك عقد، راجعه قبل ما تمضي."),
    (r"فصل|مرتب|عامل|موظف|إجاز|جزاء|استقالة", "استشارة قانون العمل", "HIGH_INTENT", "لو موقفك متعلق بالشغل، احكي التفاصيل الأساسية قبل اتخاذ خطوة."),
    (r"شركة|شريك|مدير|تأسيس|جمعية|حصة", "خدمات الشركات", "BUSINESS_INTENT", "لو الموضوع يخص شركة، خلّي المخاطر القانونية تتراجع قبل القرار."),
    (r"إيصال|شيك|دين|فلوس|مديون", "استشارة مدنية وتجارية", "LEGAL_PROBLEM", "لو معاك مستند أو مطالبة مالية، راجع موقفك القانوني أولًا."),
]

VOICE_PROFILE = {
    "version": "khyrat-v1",
    "principles": "مصري واضح؛ قانون دقيق؛ شرح عملي؛ حاسم بدون تهويل؛ لا ادعاء يقين في الوقائع غير المعروفة.",
    "preferred_openings": "سؤال من الواقع؛ خطأ شائع؛ موقف قصير؛ معلومة تصحح اعتقادًا؛ ماذا تفعل الآن؟",
    "forbidden": "لغة AI نمطية؛ مقدمات طويلة؛ تخويف بلا سند؛ وعود بنتيجة قضائية؛ حشو قانوني غير لازم؛ تكرار نفس الزاوية.",
    "tone": "مهني، مصري، مباشر، إنساني، تعليمي، وعملي.",
    "cta": "دعوة للتعليق أو المشاركة أو الاستفسار العام، مع تجنب تحويل المنشور إلى إعلان مباشر بلا قيمة.",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _ensure_sheet(service, spreadsheet_id: str, name: str, headers: list[str]) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    titles = {str(s.get("properties", {}).get("title", "")).casefold() for s in metadata.get("sheets", [])}
    if name.casefold() not in titles:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [{"addSheet": {"properties": {"title": name}}}]}).execute()
    service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=f"{name}!A1:{chr(64 + len(headers))}1", valueInputOption="RAW", body={"values": [headers]}).execute()


def ensure_system_sheets(service, spreadsheet_id: str) -> None:
    for name, headers in SYSTEM_SHEETS.items():
        _ensure_sheet(service, spreadsheet_id, name, headers)


def _append(service, spreadsheet_id: str, sheet: str, values: list[Any]) -> None:
    service.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=f"{sheet}!A:Z", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": [["" if v is None else str(v) for v in values]]}).execute()


def service_mapping(topic: str) -> tuple[str, str, str]:
    text = str(topic or "")
    for pattern, service, intent, cta in SERVICE_RULES:
        if re.search(pattern, text):
            return service, intent, cta
    return "استشارة قانونية عامة", "EDUCATIONAL", "لو عندك موقف مشابه، اكتب السؤال العام في التعليقات."


def choose_experiment(topic: str, angle: str) -> tuple[str, str, str]:
    bucket = int(hashlib.sha1(f"{topic}|{angle}".encode("utf-8")).hexdigest()[:8], 16) % 4
    variants = [("HOOK", "QUESTION"), ("HOOK", "CASE"), ("CTA", "SHARE"), ("FORMAT", "REEL")]
    variable, variant = variants[bucket]
    experiment_id = _id("EXP", topic, angle, variable, variant)
    hypothesis = {
        "QUESTION": "السؤال المباشر يرفع التعليقات.",
        "CASE": "الحالة الواقعية ترفع وقت القراءة والتفاعل.",
        "SHARE": "CTA المشاركة ترفع التوزيع العضوي.",
        "REEL": "الفيديو القصير يوسع الوصول لموضوع ناجح.",
    }[variant]
    return experiment_id, variable, variant + " | " + hypothesis


def build_content_tree(topic: str, angle: str, objective: str, platform: str) -> list[dict[str, str]]:
    parent = _id("TREE", topic, angle, platform)
    return [{
        "lineage_id": _id("LIN", parent, asset), "parent_id": parent, "asset_type": asset,
        "topic": topic, "angle": angle, "platform": platform, "objective": objective,
    } for asset in DERIVATIVE_TYPES]


def record_publication_intelligence(service, spreadsheet_id: str, *, source_row_id: str, topic: str, angle: str, objective: str, platform: str, post_id: str) -> None:
    try:
        ensure_system_sheets(service, spreadsheet_id)
        service_name, intent, cta = service_mapping(topic)
        experiment_id, variable, experiment = choose_experiment(topic, angle)
        tree = build_content_tree(topic, angle, objective, platform)
        root = tree[0]["parent_id"]
        for node in tree:
            _append(service, spreadsheet_id, "ContentLineage", [node["lineage_id"], node["parent_id"], source_row_id, node["topic"], node["asset_type"], node["angle"], node["platform"], node["objective"], service_name, experiment_id, _now()])
        _append(service, spreadsheet_id, "ContentExperiments", [experiment_id, post_id, variable, experiment.split(" | ")[0], experiment.split(" | ", 1)[1], "ACTIVE", _now()])
        _append(service, spreadsheet_id, "ConversionMap", [topic, service_name, intent, cta, "COMMENT_OR_MESSAGE"])
        _append(service, spreadsheet_id, "VoiceProfile", [VOICE_PROFILE["version"], VOICE_PROFILE["principles"], VOICE_PROFILE["preferred_openings"], VOICE_PROFILE["forbidden"], VOICE_PROFILE["tone"], VOICE_PROFILE["cta"], _now()])
        print(f"Content system: lineage={root} derivatives={len(tree)} service={service_name} experiment={experiment_id}")
    except Exception as exc:
        print(f"Content system intelligence logging failed (non-blocking): {exc}")


def classify_feedback(text: str) -> tuple[str, str, str]:
    value = str(text or "").strip()
    low = value.casefold()
    if any(x in low for x in ("ازاي", "إزاي", "ماذا أفعل", "اعمل ايه", "أعمل ايه", "كيف")):
        intent = "HOW_TO"
    elif any(x in low for x in ("هل", "ينفع", "يجوز", "صح", "خطأ")):
        intent = "QUESTION"
    elif any(x in low for x in ("عندي", "حصل معايا", "موقفي", "حالتي")):
        intent = "CASE"
    else:
        intent = "DISCUSSION"
    sentiment = "NEGATIVE" if any(x in low for x in ("مش فاهم", "غلط", "مشكلة", "ظلم", "خسرت")) else "POSITIVE" if any(x in low for x in ("شكرا", "مفيد", "تمام", "وضح")) else "NEUTRAL"
    topic_signal = value[:180]
    return intent, sentiment, topic_signal


def record_feedback(service, spreadsheet_id: str, *, post_id: str, platform: str, text: str) -> None:
    intent, sentiment, topic_signal = classify_feedback(text)
    opportunity = {"HOW_TO": "شرح خطوات عملية", "QUESTION": "FAQ أو Myth/Fact", "CASE": "Case Study أو رد متخصص", "DISCUSSION": "منشور نقاشي"}[intent]
    _append(service, spreadsheet_id, "AudienceFeedback", [_id("FB", post_id, text), post_id, platform, text, intent, sentiment, topic_signal, opportunity, _now()])


def winner_score(metrics: dict[str, float], baseline: dict[str, float] | None = None) -> float:
    base = baseline or {}
    weights = {"reach": .20, "impressions": .10, "reactions": .15, "comments": .20, "shares": .15, "saves": .10, "clicks": .05, "leads": .05}
    score = 0.0
    for key, weight in weights.items():
        value = float(metrics.get(key, 0) or 0)
        ref = float(base.get(key, 0) or 0)
        normalized = min(value / ref, 3.0) / 3.0 if ref > 0 else (1.0 if value > 0 else 0.0)
        score += normalized * weight * 100
    return round(score, 2)


def winner_tier(score: float) -> str:
    return "S" if score >= 80 else "A" if score >= 60 else "B" if score >= 40 else "C"


def next_actions_for_winner(tier: str) -> str:
    return {"S": "REEL, PART_2, CASE_STUDY, FAQ, CTA", "A": "FOLLOW_UP, FAQ, REEL", "B": "TEST_NEW_HOOK", "C": "DO_NOT_RECYCLE_YET"}[tier]


def update_winner(service, spreadsheet_id: str, *, post_id: str, topic: str, metrics: dict[str, float], baseline: dict[str, float] | None = None) -> float:
    score = winner_score(metrics, baseline)
    tier = winner_tier(score)
    _append(service, spreadsheet_id, "ContentWinners", [post_id, topic, score, tier, json.dumps(metrics, ensure_ascii=False), next_actions_for_winner(tier), _now()])
    return score


def build_authority_rows(post_rows: list[dict[str, str]], winner_rows: list[dict[str, str]]) -> list[list[str]]:
    groups: dict[str, list[float]] = {}
    winners: dict[str, int] = {}
    for row in post_rows:
        cluster = str(row.get("الموضوع", "")).strip() or "غير مصنف"
        groups.setdefault(cluster, []).append(1.0)
    for row in winner_rows:
        cluster = str(row.get("Topic", "")).strip() or "غير مصنف"
        winners[cluster] = winners.get(cluster, 0) + 1
    rows = []
    for cluster, items in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        count = len(items)
        win = winners.get(cluster, 0)
        coverage = round(min(100.0, count * 10.0), 2)
        status = "AUTHORITY" if win >= 2 and count >= 5 else "BUILD" if count < 5 else "STABLE"
        rows.append([cluster, count, win, "", coverage, status, _now()])
    return rows[:100]


def write_voice_profile(service, spreadsheet_id: str) -> None:
    _ensure_sheet(service, spreadsheet_id, "VoiceProfile", SYSTEM_SHEETS["VoiceProfile"])
    _append(service, spreadsheet_id, "VoiceProfile", [VOICE_PROFILE["version"], VOICE_PROFILE["principles"], VOICE_PROFILE["preferred_openings"], VOICE_PROFILE["forbidden"], VOICE_PROFILE["tone"], VOICE_PROFILE["cta"], _now()])
