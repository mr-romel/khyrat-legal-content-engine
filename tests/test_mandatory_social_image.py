from pathlib import Path


def test_social_publisher_never_downgrades_to_text_only():
    source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "IMAGE_REQUIRED_BLOCKED" in source
    assert "IMAGE_UNAVAILABLE_BLOCKED" in source
    assert "publish_text_to_linkedin" not in source
    assert "publish_text(" not in source
    assert "continuing with text-only publication" not in source
    assert "TEXT_ONLY_FALLBACK" not in source


def test_failed_image_repairs_remain_retryable():
    source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert 'repair_attempted = qa in {"REPAIRED_SINGLE_GENERATION", "IMAGE_REPAIR_COMPLETE"}' in source
    assert 'qa.startswith("IMAGE_REPAIR_")' not in source


def test_pollinations_secret_is_wired_to_core_publisher():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "publish-scheduled.yml").read_text(encoding="utf-8")
    generator = (Path(__file__).resolve().parents[1] / "src" / "image_generator.py").read_text(encoding="utf-8")
    assert "POLLINATIONS_API_KEY: ${{ secrets.POLLINATIONS_API_KEY }}" in workflow
    assert "def _generate_with_pollinations()" in generator
    assert "POLLINATIONS_IMAGE_GENERATION" in generator



def test_social_image_qa_unavailable_or_rejected_blocks_publication():
    source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "IMAGE_QA_UNAVAILABLE_BLOCKED" in source
    assert "IMAGE_QA_REJECTED_BLOCKED" in source
    assert "IMAGE_QA_BLOCKED" in source
    assert "QA_UNAVAILABLE_ACCEPTED" not in source
    assert "ACCEPTED_WITH_WARNINGS" not in source
    assert "isinstance(image_exc, ImageQAError)" in source
    assert "Image contains a woman or girl; semantic QA rejected the image" in source
    assert "IMAGE_QA_UNAVAILABLE_BLOCKED during published-image repair" in source
    assert "raise ImageQAError(image_qa_summary) from qa_exc" in source
    assert "raise ImageQAError(" in source
    assert "Replacement image failed visual relevance/text QA" in source


def test_image_qa_retry_budget_is_persistent_and_bounded():
    source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "MAX_IMAGE_QA_ATTEMPTS = 6" in source
    assert "IMAGE_QA_ATTEMPTS_PER_RUN = 3" in source
    assert "IMAGE_QA_RETRY_BUDGET_EXHAUSTED" in source
    assert 'error.startswith("IMAGE_QA_BLOCKED:")' in source
    assert "Avoid people and hands when possible" not in source
    assert "attempt_number >= attempt_limit" in source
    assert "image_qa_attempt >= 3" not in source


def test_image_regeneration_uses_qa_corrections_without_removing_original_brief():
    source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "build_image_regeneration_brief(visual_description, regeneration_notes)" in source
    generator = (Path(__file__).resolve().parents[1] / "src" / "image_generator.py").read_text(encoding="utf-8")
    assert "Keep every required subject, person, action" in generator
    assert "do not add new exclusions" in generator


def test_known_abstract_legal_angle_overrides_stale_sheet_image_brief():
    main_source = (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert "deterministic_scene = _deterministic_legal_scene(topic, post)" in main_source
    assert "if deterministic_scene:" in main_source
    assert "return deterministic_scene" in main_source
    assert "generate_image_scene_from_post(api_key=api_key, model=model, post=post, topic=topic)" in main_source
