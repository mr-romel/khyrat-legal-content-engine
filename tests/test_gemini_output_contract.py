from gemini import _validate_data


def test_core_legal_draft_does_not_require_or_generate_image_brief():
    result = _validate_data({
        "post": "A legally grounded draft with enough content for downstream review.",
        "review_level": "CLEAR",
        "review_flags": [],
        "legal_sources_used": [],
        "hook_pattern": "question",
    })

    assert result["post"].startswith("A legally grounded draft")
    assert result["image_brief"] == ""
    assert result["image_mode"] == "CONTEXT_ONLY"


def test_criminal_contribution_checklist_uses_stable_no_people_visual_scene():
    from gemini import _deterministic_legal_scene

    scene = _deterministic_legal_scene(
        "المساهمة الجنائية — زاوية جديدة: Checklist عملية قبل بدء أي إجراء",
        "قائمة مراجعة عملية قبل اتخاذ أي إجراء في موضوع المساهمة الجنائية.",
    )

    assert scene is not None
    assert "checklist" in scene.lower()
    assert "criminal participation" in scene.lower()
    assert "black pen" in scene
    assert "Use the requested output aspect ratio exactly" in scene


def test_deterministic_visual_scene_does_not_override_unrelated_legal_topics():
    from gemini import _deterministic_legal_scene

    assert _deterministic_legal_scene(
        "القضايا العمالية",
        "قائمة مراجعة لمستحقات العامل.",
    ) is None
