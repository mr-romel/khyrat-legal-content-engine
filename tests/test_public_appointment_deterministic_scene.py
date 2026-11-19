from gemini import _deterministic_legal_scene


def test_public_appointment_scene_makes_vacancy_notice_the_primary_subject():
    scene = _deterministic_legal_scene(
        "الوظيفة العامة والتعيين",
        "ثلاث علامات تحذيرية قبل اتخاذ قرار التعيين في الوظيفة العامة.",
    )
    assert scene is not None
    assert "public-sector job vacancy announcement" in scene
    assert "dominant subject" in scene
    assert "red circular" in scene
    assert "applicant's hand" in scene
    assert "empty visitor chair" in scene
    assert "desk calendar" in scene
