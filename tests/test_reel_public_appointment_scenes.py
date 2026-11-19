from reel_pipeline import post_visual_terms


def test_public_service_appointment_uses_five_explicit_vacancy_scenes():
    scenes = post_visual_terms(
        "زاوية جديدة: 3 علامات تحذيرية قبل اتخاذ قرار التعيين في الوظيفة العامة",
        "الوظيفة العامة والتعيين",
    )
    assert len(scenes) == 8
    assert all("vacancy announcement" in scene or "public employment vacancy notice" in scene or "public-sector recruitment" in scene or "public vacancy announcement" in scene for scene in scenes[:5])
    assert "notice board" in scenes[0]
    assert "submission tray" in scenes[1]
    assert "recruitment committee" in scenes[2]
