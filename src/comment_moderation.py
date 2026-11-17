from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommentDecision:
    category: str
    intent: str
    action: str
    confidence: float
    reason: str


_SPAM = re.compile(r"(https?://|www\\.|كسب\\s+فلوس|اربح|استثمار\\s+مضمون|تسويق|اعلان|تابعني\\s+خاص|واتساب\\s+للتوظيف)", re.I)
_LEAD = re.compile(r"(محتاج\\s*(محامي|محاميه|محاماة)|عايز\\s*(محامي|استشارة)|محتاج\\s*استشارة|عايز\\s*اتواصل|رقم\\s*المكتب|اتواصلوا?\\s*معايا|توكيل|تولي\\s*قضيه|ارفع\\s*قضيه|عندي\\s*قضيه)", re.I)
_COMPLAINT = re.compile(r"(نصب|نصاب|مش\\s*بترد|محدش\\s*رد|تجربه\\s*سيئه|شكوى|شكوى|هشتكي|بلاغ|مضلل|معلومات\\s*غلط)", re.I)
_SENSITIVE = re.compile(r"(رقم\\s*قومي|بطاقه|عنواني|رقم\\s*القضيه|رقم\\s*المحضر|اسم\\s*الخصم|بياناتي|مرفق\\s*صوره|هرفع\\s*المستند)", re.I)
_THANKS = re.compile(r"(شكرا|شكرًا|متشكر|جزاك\\s*الله|ربنا\\s*يكرمك|مفيد|تسلم|بارك\\s*الله|احسنتم)", re.I)
_QUESTION = re.compile(r"(\\?|؟|ازاي|إزاي|كيف|هل|متى|امتى|فين|ما\\s*هو|ايه|إيه|ينفع|يجوز|القانون\\s*بيقول|اعمل\\s*ايه)", re.I)


def classify_comment(text: str) -> CommentDecision:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return CommentDecision("EMPTY", "UNKNOWN", "REVIEW", 0.99, "empty_comment")
    if _SPAM.search(value):
        return CommentDecision("SPAM", "PROMOTION_OR_LINK", "SKIP", 0.96, "spam_pattern")
    if re.search(r"(?<!\\d)\\d{14}(?!\\d)|01[0-2,5]\\d{8}|[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", value, re.I):
        return CommentDecision("SENSITIVE", "PERSONAL_DATA", "REVIEW", 0.99, "possible_personal_data")
    if _SENSITIVE.search(value):
        return CommentDecision("SENSITIVE", "CASE_SPECIFIC_OR_PRIVATE_DATA", "REVIEW", 0.95, "private_case_details")
    if _COMPLAINT.search(value):
        return CommentDecision("COMPLAINT", "SERVICE_FEEDBACK", "REVIEW", 0.93, "complaint_or_reputation")
    if _LEAD.search(value):
        return CommentDecision("LEAD", "LEGAL_SERVICE_REQUEST", "AUTO_REPLY", 0.91, "explicit_contact_or_representation_intent")
    if _QUESTION.search(value):
        return CommentDecision("LEGAL_QUESTION", "GENERAL_OR_CASE_QUESTION", "AUTO_REPLY", 0.82, "question_requires_non_advisory_response")
    if _THANKS.search(value):
        return CommentDecision("POSITIVE", "THANKS_OR_POSITIVE_FEEDBACK", "AUTO_REPLY", 0.90, "positive_feedback")
    return CommentDecision("OTHER", "UNCLEAR", "REVIEW", 0.55, "unclear_intent")


def build_public_reply(decision: CommentDecision, *, whatsapp_url: str = "https://wa.me/201022718375", phone: str = "01022718375") -> str:
    if decision.action != "AUTO_REPLY":
        return ""
    if decision.category == "LEAD":
        return f"أهلًا بحضرتك. للتواصل مع المكتب وطلب تقييم أولي للموقف، تقدر تتصل على {phone} أو تبعت رسالة واتساب من هنا: {whatsapp_url}"
    if decision.category == "LEGAL_QUESTION":
        return f"شكرًا على سؤالك. الإجابة القانونية بتتوقف على تفاصيل الواقعة والمستندات، ومش مناسب إصدار رأي نهائي من تعليق عام. لو محتاج تقييم لحالتك، تقدر تتواصل مع المكتب على {phone} أو واتساب: {whatsapp_url}"
    if decision.category == "POSITIVE":
        return "شكرًا على تعليقك. سعيدين إن المحتوى كان مفيد لحضرتك، ونتمنى تتابعنا للمزيد من المعلومات القانونية العملية"
    return ""


def requires_human_review(decision: CommentDecision) -> bool:
    return decision.action == "REVIEW"
