from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


SYSTEM_SHEETS = {
    "ContentLineage": ["lineage_id", "parent_id", "content_id", "content_type", "topic", "angle", "platform", "created_at"],
    "AudienceFeedback": ["feedback_id", "platform", "post_id", "text", "intent", "sentiment", "topic_signal", "created_at"],
    "ContentWinners": ["content_id", "score", "tier", "metrics", "next_actions", "updated_at"],
    "AuthorityMap": ["topic", "content_count", "winner_count", "coverage", "authority_status", "updated_at"],
    "ConversionMap": ["content_id", "audience_intent", "service", "cta", "lead_signal", "updated_at"],
    "VoiceProfile": ["profile_id", "version", "principles", "preferred_openings", "forbidden_styles", "tone", "cta", "updated_at"],
    "ContentExperiments": ["experiment_id", "content_id", "hypothesis", "variable", "variant", "status", "result", "created_at"],
    "ContentMetrics": ["content_id", "platform", "views", "likes", "comments", "shares", "saves", "clicks", "leads", "published_at"],
}

DERIVATIVE_TYPES = (
    "POST", "REEL", "CAROUSEL", "FAQ", "CASE_STUDY", "MYTH_FACT",
    "CHECKLIST", "WARNING", "COMPARISON", "QUESTION", "FOLLOW_UP", "CTA_ASSET",
)

SERVICE_RULES = (
    (("عقد", "اتفاق", "بند", "شرط"), "مراجعة وصياغة العقود", "CONTRACT_REVIEW", "هل عندك عقد أو بند مشابه؟ ابعته للمراجعة القانونية."),
    (("فصل", "مرتب", "عامل", "موظف", "إجاز", "جزاء", "استقالة"), "استشارة قانون العمل", "LABOR_CONSULT", "لو عندك موقف عملي مشابه، ابعت التفاصيل قبل ما تاخد إجراء."),
    (("شركة", "شريك", "مدير", "تأسيس", "جمعية", "حصة"), "خدمات الشركات", "CORPORATE", "لو الموضوع يخص شركة أو شراكة، نقدر نراجع موقفك قانونيًا."),
    (("إيصال", "شيك", "دين", "فلوس", "مديون"), "استشارة مدنية وتجارية", "CIVIL_COMMERCIAL", "لو عندك مستند أو مديونية، اعرف موقفك القانوني قبل التحرك."),
)

VOICE_PROFILE = {
    "profile_id": "khyrat-voice",
    "version": "khyrat-v1",
    "principles": "مصري واضح؛ مباشر؛ مهني؛ دقيق قانونيًا؛ عملي؛ بدون تهويل أو وعود؛ سهل على المتلقي.",
    "preferred_openings": "سؤال واقعي، موقف شائع، تصحيح معلومة، تحذير عملي.",
    "forbidden_styles": "لغة روبوتية، مبالغة، تخويف، حشو، مصطلحات قانونية بلا شرح، CTA ضاغطة.",
    "tone": "محامي مصري يشرح للمصري ببساطة واحترام.",
    "cta": "لو موقفك مختلف، ابعت التفاصيل عشان تعرف التصرف القانوني الأنسب.",
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
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": name}}}]},
        ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{name}!A1:{chr(64 + len(headers))}1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()


def ensure_system_sheets(service, spreadsheet_id: str) -> None:
    for name, headers in SYSTEM_SHEETS.items():
        _ensure_sheet(service, spreadsheet_id, name, headers)


def service_mapping(topic: str) -> tuple[str, str, str]:
    text = str(topic or "")
    for patterns, service, intent, cta in SERVICE_RULES:
        if any(p in text for p in patterns):
            return service, intent, cta
    return "استشارة قانونية", "GENERAL_LEGAL", VOICE_PROFILE["cta"]


def choose_experiment(topic: str, angle: str) -> dict[str, str]:
    bucket = int(hashlib.sha1(f"{topic}|{angle}".encode("utf-8")).hexdigest()[:8], 16) % 3
    variants = (
        ("HOOK", "اختبار افتتاحية سؤال واقعي مقابل افتتاحية تحذير"),
        ("CTA", "اختبار CTA معلوماتية مقابل CTA تواصلية"),
        ("ANGLE", "اختبار زاوية عملية مقابل زاوية تصحيح اعتقاد"),
    )
    variable, hypothesis = variants[bucket]
    return {"variable": variable, "hypothesis": hypothesis, "variant": f"V{bucket + 1}"}


def build_content_tree(topic: str, angle: str, objective: str = "EDUCATE", platform: str = "FACEBOOK") -> list[dict[str, str]]:
    root_id = _id("topic", topic, angle)
    now = _now()
    rows = []
    for derivative in DERIVATIVE_TYPES:
        content_id = _id("content", root_id, derivative)
        rows.append({
            "lineage_id": _id("lineage", root_id, derivative),
            "parent_id": root_id,
            "content_id": content_id,
            "content_type": derivative,
            "topic": topic,
            "angle": angle,
            "platform": platform,
            "objective": objective,
            "created_at": now,
        })
    return rows


def _append(service, spreadsheet_id: str, sheet: str, values: list[Any]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


def record_publication_intelligence(service, spreadsheet_id: str, *, content_id: str, topic: str, angle: str, objective: str, platform: str) -> None:
    try:
        ensure_system_sheets(service, spreadsheet_id)
        now = _now()
        for row in build_content_tree(topic, angle, objective, platform):
            _append(service, spreadsheet_id, "ContentLineage", [row[k] for k in SYSTEM_SHEETS["ContentLineage"]])
        experiment = choose_experiment(topic, angle)
        _append(service, spreadsheet_id, "ContentExperiments", [
            _id("exp", content_id), content_id, experiment["hypothesis"], experiment["variable"], experiment["variant"], "ACTIVE", "", now,
        ])
        service_name, audience_intent, cta = service_mapping(topic)
        _append(service, spreadsheet_id, "ConversionMap", [content_id, audience_intent, service_name, cta, "", now])
        _append(service, spreadsheet_id, "VoiceProfile", [
            VOICE_PROFILE["profile_id"], VOICE_PROFILE["version"], VOICE_PROFILE["principles"],
            VOICE_PROFILE["preferred_openings"], VOICE_PROFILE["forbidden_styles"], VOICE_PROFILE["tone"], VOICE_PROFILE["cta"], now,
        ])
    except Exception:
        # Intelligence is intentionally non-blocking for the publishing pipeline.
        return


def classify_feedback(text: str) -> tuple[str, str, str]:
    low = str(text or "").strip().casefold()
    # HOW_TO takes precedence over CASE because Egyptian users commonly combine
    # a personal context marker ("عندي") with a direct action question ("أعمل إيه؟").
    how_to_phrases = (
        "ازاي", "إزاي", "ماذا أفعل", "اعمل ايه", "أعمل ايه", "اعمل إيه", "أعمل إيه", "كيف",
    )
    if any(x in low for x in how_to_phrases):
        intent = "HOW_TO"
    elif any(x in low for x in ("هل", "ينفع", "يجوز", "صح", "خطأ")):
        intent = "QUESTION"
    elif any(x in low for x in ("عندي", "حصل معايا", "موقفي", "حالتي")):
        intent = "CASE"
    else:
        intent = "GENERAL"
    if any(x in low for x in ("مش", "لا", "مشكلة", "خايف", "متضايق")):
        sentiment = "CONCERN"
    elif any(x in low for x in ("شكرا", "ممتاز", "حلو", "جامد")):
        sentiment = "POSITIVE"
    else:
        sentiment = "NEUTRAL"
    topic_signal = low[:180]
    return intent, sentiment, topic_signal


def record_feedback(service, spreadsheet_id: str, *, platform: str, post_id: str, text: str) -> None:
    intent, sentiment, topic_signal = classify_feedback(text)
    _append(service, spreadsheet_id, "AudienceFeedback", [
        _id("feedback", platform, post_id, text), platform, post_id, text, intent, sentiment, topic_signal, _now(),
    ])


def winner_score(metrics: dict[str, float], baseline: dict[str, float] | None = None) -> float:
    baseline = baseline or {}
    weights = {"views": .15, "likes": .15, "comments": .20, "shares": .20, "saves": .15, "clicks": .10, "leads": .05}
    score = 0.0
    for key, weight in weights.items():
        value = float(metrics.get(key, 0) or 0)
        base = float(baseline.get(key, 0) or 0)
        if base > 0:
            value = value / base
        score += value * weight
    return round(score, 4)


def winner_tier(score: float) -> str:
    if score >= 2:
        return "S"
    if score >= 1.35:
        return "A"
    if score >= .85:
        return "B"
    return "C"


def next_actions_for_winner(tier: str) -> str:
    return {
        "S": "PART_2,REEL,CASE_STUDY,FAQ,CTA_ASSET",
        "A": "PART_2,REEL,FAQ",
        "B": "FOLLOW_UP,QUESTION",
        "C": "KEEP_OR_REWORK_HOOK",
    }.get(tier, "REVIEW")


def update_winner(service, spreadsheet_id: str, content_id: str, metrics: dict[str, float], baseline: dict[str, float]) -> None:
    score = winner_score(metrics, baseline)
    tier = winner_tier(score)
    _append(service, spreadsheet_id, "ContentWinners", [content_id, score, tier, str(metrics), next_actions_for_winner(tier), _now()])


def build_authority_rows(post_rows: list[dict[str, Any]], winner_rows: list[dict[str, Any]]) -> list[list[Any]]:
    stats: dict[str, dict[str, int]] = {}
    for row in post_rows:
        topic = str(row.get("topic") or row.get("Topic") or "").strip()
        if not topic:
            continue
        stats.setdefault(topic, {"content_count": 0, "winner_count": 0})["content_count"] += 1
    for row in winner_rows:
        content_id = str(row.get("content_id") or "")
        for topic, data in stats.items():
            if topic and topic in content_id:
                data["winner_count"] += 1
    now = _now()
    return [[topic, data["content_count"], data["winner_count"], "COVERED" if data["content_count"] else "", "BUILD" if data["content_count"] < 3 else "ESTABLISHED", now] for topic, data in stats.items()]


def write_voice_profile(service, spreadsheet_id: str) -> None:
    _append(service, spreadsheet_id, "VoiceProfile", [
        VOICE_PROFILE["profile_id"], VOICE_PROFILE["version"], VOICE_PROFILE["principles"],
        VOICE_PROFILE["preferred_openings"], VOICE_PROFILE["forbidden_styles"], VOICE_PROFILE["tone"], VOICE_PROFILE["cta"], _now(),
    ])
