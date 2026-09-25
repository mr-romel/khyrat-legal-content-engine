from content_system import content_fingerprint, infer_audience_persona, choose_visual_concept
from engagement_strategy import choose_comment_count, comment_schedule_offsets
from social_content import sanitize_social_copy


def test_social_copy_human_cleanup():
    value = sanitize_social_copy('هذا اختبار. "اقتباس" مع ذكاء اصطناعي.')
    assert '"' not in value
    assert "ذكاء اصطناعي" not in value
    assert not value.endswith(".")


def test_comment_count_shared_and_variable():
    a = choose_comment_count("topic-a|post-a")
    b = choose_comment_count("topic-b|post-b")
    assert 3 <= a <= 7
    assert 3 <= b <= 7
    assert comment_schedule_offsets(a) == [15 * i for i in range(a)]


def test_persona_and_visual_strategy():
    persona, goal = infer_audience_persona("قرار شركة وتعاقد", "مراجعة قبل التوقيع", "LINKEDIN")
    assert "شركة" in persona
    assert goal
    concept_id, concept = choose_visual_concept("قرار شركة", "مراجعة عقد")
    assert concept_id
    assert concept


def test_content_fingerprint_changes_with_platform():
    fb = content_fingerprint(topic="عقد", post="قبل ما تمضي راجع البند", angle="وقاية", objective="LEAD_GENERATION", platform="FACEBOOK")
    li = content_fingerprint(topic="عقد", post="قبل ما تمضي راجع البند", angle="وقاية", objective="LEAD_GENERATION", platform="LINKEDIN")
    assert fb["fingerprint"] != li["fingerprint"]
    assert fb["audience"]
    assert fb["visual_concept"]
