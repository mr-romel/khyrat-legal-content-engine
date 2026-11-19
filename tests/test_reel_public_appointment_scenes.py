from reel_pipeline import post_visual_terms


def test_public_service_appointment_uses_text_free_recruitment_process_scenes():
    scenes = post_visual_terms(
        "زاوية جديدة: 3 علامات تحذيرية قبل اتخاذ قرار التعيين في الوظيفة العامة",
        "الوظيفة العامة والتعيين",
    )
    assert len(scenes) == 8
    assert "government employment office" in scenes[0]
    assert "recruitment waiting area" in scenes[1]
    assert "recruitment interview" in scenes[2]
    assert all(
        forbidden not in scene.casefold()
        for scene in scenes
        for forbidden in ("notice board", "vacancy poster", "application form", "submission tray")
    )
    assert all(
        any(term in scene.casefold() for term in ("no signs", "no signage", "no paperwork", "no papers", "no documents", "no posters", "no writing", "no visible logos"))
        for scene in scenes
    )
