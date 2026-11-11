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
