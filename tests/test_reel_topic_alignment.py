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


def test_identity_impersonation_uses_its_own_reel_visual_family():
    from reel_pipeline import _visual_topic_family, post_visual_terms

    topic = "انتحال الشخصية"
    assert _visual_topic_family(topic) == "identity_impersonation"
    scenes = post_visual_terms("إجراءات التحقق من الهوية ومواجهة انتحال الشخصية", topic)
    assert len(scenes) >= 5
    assert len(set(scenes)) >= 5
    assert all(
        any(term in scene.lower() for term in ("identity", "fingerprint", "id card", "account", "verification"))
        for scene in scenes
    )


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


def test_video_description_removes_mixed_english_gibberish_and_uses_approved_arabic_post():
    from video_metadata import build_video_description

    description = build_video_description(
        topic="ضوابط ترخيص العمالة",
        post=(
            "يجب على صاحب العمل مراجعة تراخيص مزاولة المهن والاحتفاظ بالمستندات "
            "ومراجعة تاريخ التعيين قبل اتخاذ قرار التشغيل."
        ),
        script=(
            "كتير من OWNER OF BUSINESSES يconsider ترريب العمال كإجراء روتيني "
            "لكن التشغيل بدون ترريب يعرض المنشأة لمخاطر قانونية."
        ),
        platform="youtube",
    )
    assert "OWNER" not in description
    assert "BUSINESSES" not in description
    assert "يجب على صاحب العمل" in description
    assert "واتساب" not in description  # The fixed WhatsApp CTA is a URL, not generated prose.
    assert "https://wa.me/201022718375" in description



def test_impersonation_topic_wins_over_incidental_employee_context():
    assert _topic_family("انتحال الشخصية والتحقق من هوية الموظف") == "impersonation"
    description = build_video_description(
        topic="انتحال الشخصية",
        post="انتحال الشخصية باستخدام بيانات موظف آخر يستلزم التحقق من مصدر الحساب والرسائل.",
        script="لو حد استخدم بيانات موظف تاني وانتحل شخصيته، راجع مصدر الحساب والرسائل وسجل الدخول.",
        platform="facebook",
    )
    assert "انتحال الشخصية" in description


def test_public_service_topic_wins_over_generic_employee_words():
    assert _topic_family("الوظيفة العامة والتعيين") == "public_service"
    assert _topic_family("النقل كجزاء تأديبي للموظف العام") == "public_service"

def test_video_metadata_recognizes_public_service_and_impersonation_subjects():
    from video_metadata import _topic_family

    assert _topic_family("الوظيفة العامة والتعيين") == "public_service"
    assert _topic_family("انتحال الشخصية") == "impersonation"

def test_privacy_violation_topic_is_not_misclassified_by_editorial_word_process():
    from reel_pipeline import _visual_topic_family, _visual_topic_content_aligned

    topic = "انتهاك حرمة الحياة الخاصة — زاوية جديدة: Checklist عملية قبل بدء أي إجراء"
    post = "انتهاك حرمة الحياة الخاصة له صور متعددة، منها الاعتداء على البيانات الشخصية أو إفشائها دون سند."
    assert _visual_topic_family(topic) == "privacy_violation"
    assert _visual_topic_family("عملية التحقق من المستندات") == "general"
    assert _visual_topic_content_aligned(topic, post)


def test_employment_classifier_still_recognizes_actual_employment_terms():
    from reel_pipeline import _visual_topic_family

    assert _visual_topic_family("حقوق العامل في علاقة العمل") == "employment"
    assert _visual_topic_family("العمل دون عقد مكتوب") == "employment"


def test_privacy_family_precedes_generic_criminal_wording():
    from reel_pipeline import _visual_topic_family

    assert _visual_topic_family("جريمة انتهاك حرمة الحياة الخاصة") == "privacy_violation"

