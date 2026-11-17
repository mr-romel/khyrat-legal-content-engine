from comment_moderation import classify_comment, build_public_reply, requires_human_review


def test_explicit_legal_service_request_gets_safe_contact_reply():
    decision = classify_comment("محتاج محامي في قضية تعويض وعايز أتواصل")
    assert decision.category == "LEAD"
    assert decision.intent == "LEGAL_SERVICE_REQUEST"
    assert decision.action == "AUTO_REPLY"
    reply = build_public_reply(decision)
    assert "01022718375" in reply
    assert "wa.me/201022718375" in reply
    assert "حكم" not in reply


def test_general_legal_question_gets_non_advisory_reply():
    decision = classify_comment("هل ينفع أعمل تظلم؟")
    assert decision.category == "LEGAL_QUESTION"
    assert decision.action == "AUTO_REPLY"
    reply = build_public_reply(decision)
    assert "تفاصيل الواقعة والمستندات" in reply
    assert "مش مناسب إصدار رأي نهائي" in reply


def test_personal_data_is_never_auto_replied():
    decision = classify_comment("رقمي القومي 12345678901234 وعايز استشارة")
    assert decision.category == "SENSITIVE"
    assert requires_human_review(decision)
    assert build_public_reply(decision) == ""


def test_complaint_is_held_for_human_review():
    decision = classify_comment("محدش رد عليا ودي تجربة سيئة")
    assert decision.category == "COMPLAINT"
    assert decision.action == "REVIEW"


def test_spam_is_skipped_without_reply():
    decision = classify_comment("اربح فلوس من هنا https://spam.example")
    assert decision.category == "SPAM"
    assert decision.action == "SKIP"
    assert build_public_reply(decision) == ""


def test_positive_feedback_gets_brief_thank_you():
    decision = classify_comment("شكرا جدا المحتوى مفيد")
    assert decision.category == "POSITIVE"
    assert "شكرًا" in build_public_reply(decision)
