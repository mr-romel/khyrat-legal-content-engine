from gemini import build_editorial_brief


def test_editorial_brief_is_created_for_each_topic_with_search_and_legal_fields():
    brief = build_editorial_brief(
        "ميعاد دعوى إلغاء القرار الإداري",
        "المادة 24 من قانون مجلس الدولة",
        "منشورات سابقة عن القرارات الإدارية",
    )
    assert brief["primary_query"] == "ميعاد دعوى إلغاء القرار الإداري"
    assert brief["search_intent"]
    assert brief["target_audience"]
    assert brief["reader_job"]
    assert brief["legal_evidence"]
    assert len(brief["subquestions"]) >= 3
    assert len(brief["outline"]) >= 3
    assert brief["source_status"] == "متاحة"


def test_editorial_brief_does_not_invent_serp_metrics_or_exact_search_volume():
    brief = build_editorial_brief("منازعات الشركات", "", "")
    rendered = str(brief)
    assert "search_volume" not in rendered
    assert "ranking" not in rendered
    assert brief["source_status"].startswith("لا توجد")
