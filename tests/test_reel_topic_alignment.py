from __future__ import annotations

import pytest

from video_metadata import _topic_family, build_video_description


def test_topic_family_recognizes_core_reel_subjects():
    assert _topic_family("تهديد بإفشاء الأسرار") == "secret_threat"
    assert _topic_family("جريمة التحرش") == "harassment"
    assert _topic_family("فسخ عقد الإيجار") == "rent"
    assert _topic_family("نزاع على إيصال أمانة") == "payments"


def test_video_description_rejects_narration_from_another_subject():
    with pytest.raises(ValueError, match="Video metadata topic mismatch"):
        build_video_description(
            topic="تهديد بإفشاء الأسرار",
            post="لو حد هددك بإفشاء أسرارك، احتفظ بالدليل الأصلي وتاريخه.",
            script="لو صاحب العمل فصلك من غير سبب، راجع مستندات علاقة العمل.",
            platform="facebook",
        )


def test_video_description_accepts_matching_topic_and_narration():
    description = build_video_description(
        topic="تهديد بإفشاء الأسرار",
        post="لو حد هددك بإفشاء أسرارك، احتفظ بالدليل الأصلي وتاريخه.",
        script="لو حد هددك بإفشاء أسرارك، احتفظ بالرسالة الأصلية وتاريخها قبل أي تصرف.",
        platform="facebook",
    )
    assert "تهديد بإفشاء الأسرار" in description
    assert "الرسالة الأصلية" in description



def test_nursery_cctv_topic_gets_its_own_visual_scene_family():
    from reel_pipeline import _visual_topic_family, post_visual_terms

    topic = "حقيقة قرار إلزام الحضانات بكاميرات المراقبة والغرامات"
    assert _visual_topic_family(topic) == "nursery_surveillance"
    scenes = post_visual_terms("توضيح قانوني لأصحاب الحضانات وأولياء الأمور", topic)
    assert len(scenes) == 8
    assert all("nursery" in scene.lower() or "daycare" in scene.lower() for scene in scenes)
    assert any("CCTV" in scene for scene in scenes)


def test_reel_recovery_skips_mismatched_legal_topic_rows():
    from reel_pipeline import _visual_topic_content_aligned

    assert not _visual_topic_content_aligned(
        "التعويض عن الأضرار المدنية",
        "حقوق العامل في الفصل التعسفي ومكافأة نهاية الخدمة",
    )


def test_reel_recovery_accepts_matching_legal_topic_rows():
    from reel_pipeline import _visual_topic_content_aligned

    assert _visual_topic_content_aligned(
        "التعويض عن الأضرار المدنية",
        "يجوز طلب التعويض عن الضرر متى توافرت أركان المسؤولية المدنية.",
    )
