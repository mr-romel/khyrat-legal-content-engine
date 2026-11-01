from blogger_trend_worker import _is_foreign_jurisdiction


def test_rejects_foreign_jurisdiction_trend():
    item = {"title": "إلزام الحضانات بكاميرات مراقبة في سلطنة عمان وغرامات بالريال",
            "description": "قرار وزاري صادر في سلطنة عمان"}
    assert _is_foreign_jurisdiction(item)


def test_allows_egyptian_legal_topic_without_foreign_country_marker():
    item = {"title": "وزارة العمل تعلن ضوابط جديدة لعقود العمل",
            "description": "توضيح للمواطنين وأصحاب الأعمال في مصر"}
    assert not _is_foreign_jurisdiction(item)
