from gemini import SYSTEM_PROMPT
from gemini_chat import EDITORIAL_STYLE_PROMPT
from editorial_review import SYSTEM_PROMPT as REVIEW_SYSTEM_PROMPT


def test_authoring_instructions_require_search_intent_without_fabricating_serp_data():
    assert "نية الباحث" in SYSTEM_PROMPT
    assert "لا تدّعِ إجراء SERP review" in SYSTEM_PROMPT
    assert "لا تخترع حجم بحث" in SYSTEM_PROMPT


def test_facebook_authoring_requires_clean_egyptian_arabic_and_direct_answer():
    combined = SYSTEM_PROMPT + EDITORIAL_STYLE_PROMPT
    assert "عربية مصرية سليمة" in combined
    assert "أجب عن السؤال مباشرة" in combined
    assert "كلمات إنجليزية عشوائية" in combined
    assert "لا تضف مهلة أقصر" in combined


def test_editorial_review_repairs_mixed_language_and_checks_deadline_claims():
    assert "تدقيقًا لغويًا فعليًا" in REVIEW_SYSTEM_PROMPT
    assert "مدد طعن أقصر" in REVIEW_SYSTEM_PROMPT
    assert "لا تدّعِ مراجعة SERP" in REVIEW_SYSTEM_PROMPT
