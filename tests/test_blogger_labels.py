from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_publisher import normalize_blogger_labels


def test_blogger_labels_stay_under_combined_character_limit():
    source = ["قانون مصر", "اسأل محمود", *[f"موضوع قانوني طويل رقم {i} مع كلمات إضافية" for i in range(20)]]
    labels = normalize_blogger_labels(source)
    assert labels
    assert len(labels) <= 10
    assert len(", ".join(labels)) <= 180
    assert len({label.casefold() for label in labels}) == len(labels)


def test_blogger_labels_remove_commas_and_newlines():
    labels = normalize_blogger_labels(["عقد, عمل\nشركات", "عقد, عمل شركات"])
    assert labels == ["عقد عمل شركات"]

def test_blogger_dashboard_verifier_accepts_published_but_rejects_draft_or_scheduled():
    from blogger_ui_publisher import _is_published_dashboard_row

    assert _is_published_dashboard_row("Post title Published")
    assert _is_published_dashboard_row("عنوان المقال منشور")
    assert not _is_published_dashboard_row("Post title Draft")
    assert not _is_published_dashboard_row("Post title Scheduled")
    assert not _is_published_dashboard_row("Post title Published Draft")


def test_blogger_article_removes_leaked_ai_drafting_instructions():
    from blogger_publisher import _article_copy

    article = _article_copy({
        "title": "حقوق العامل عند الفصل",
        "lead": "يبدأ التقييم من المستندات. تعليمات صياغة الذكاء الاصطناعي: اكتب مقالًا توعويًا.",
        "meta_description": "شرح حقوق العامل والإجراءات العملية قبل اتخاذ خطوة.",
        "excerpt": "دليل عملي لفهم المستندات.",
        "sections": [
            {"heading": "ما الذي يجب مراجعته؟", "body": "راجع العقد والإخطارات وسجل الوقائع."},
            {"heading": "ما الخطوة التالية؟", "body": "تحقق من النص القانوني الساري والمواعيد."},
        ],
        "faq": [],
    })
    rendered = " ".join([
        article["title"], article["lead"], article["meta_description"],
        *(section["heading"] + " " + section["body"] for section in article["sections"]),
    ])
    assert "تعليمات صياغة الذكاء الاصطناعي" not in rendered
    assert "اكتب مقالًا توعويًا" not in rendered


def test_blogger_article_refuses_unremoved_prompt_leak():
    import pytest
    from blogger_publisher import _article_copy, BloggerPublishError

    with pytest.raises(BloggerPublishError):
        _article_copy({
            "title": "اكتب مقال عن حقوق العامل",
            "lead": "شرح قانوني مفيد للقارئ.",
            "sections": [
                {"heading": "المستندات", "body": "راجع العقد."},
                {"heading": "الإجراء", "body": "راجع المواعيد."},
            ],
        })
