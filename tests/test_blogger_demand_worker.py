import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_demand_worker import _is_foreign_jurisdiction_query


def test_foreign_jurisdiction_topics_are_rejected():
    assert _is_foreign_jurisdiction_query("رفض الورثة تقسيم الإرث في القانون الجزائري")
    assert _is_foreign_jurisdiction_query("حقوق العامل في القانون السعودي")


def test_egyptian_legal_topics_remain_eligible():
    assert not _is_foreign_jurisdiction_query("حقوق العامل عند الفصل في مصر")
    assert not _is_foreign_jurisdiction_query("إجراءات رفع دعوى تعويض")

def test_topic_similarity_catches_query_embedded_in_long_seo_title():
    from blogger_demand_worker import _similarity

    assert _similarity(
        "حقوق العامل عند الفصل",
        "حقوق العامل عند الفصل في القانون المصري: المستندات والخطوات العملية",
    ) >= 0.75
    assert _similarity(
        "حقوق العامل عند الفصل",
        "تأسيس الشركات ومسؤولية المدير",
    ) < 0.44
