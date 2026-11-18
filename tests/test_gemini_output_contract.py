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


def test_image_scene_regeneration_uses_qa_feedback_and_changes_previous_scene(monkeypatch):
    import gemini

    captured = {}
    class FakeModels:
        def generate_content(self, **kwargs):
            captured["prompt"] = kwargs["contents"]
            return type("Response", (), {
                "text": "A contemporary public-service applicant checking a posted recruitment notice at a government service counter, with a queue ticket and application folder visible."
            })()
    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "create_client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(gemini, "_deterministic_legal_scene", lambda topic, post: "A repeated generic scene.")
    result = gemini.generate_image_scene_from_post(
        api_key="test-key",
        model="test-model",
        topic="الوظيفة العامة والتعيين",
        post="يتعلق الموضوع بشروط التعيين وإجراءات التقديم للوظائف العامة.",
        previous_scene="A generic legal desk with scales and a law book.",
        qa_feedback="The image is unrelated. Show a public-service applicant reviewing a recruitment notice.",
    )
    assert "public-service applicant" in result
    assert "A generic legal desk with scales and a law book." in captured["prompt"]
    assert "The image is unrelated." in captured["prompt"]
    assert "materially different alternative scene" in captured["prompt"]
