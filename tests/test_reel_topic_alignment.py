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
