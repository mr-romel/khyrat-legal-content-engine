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
