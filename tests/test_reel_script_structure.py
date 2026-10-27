from pathlib import Path


def test_reel_prompt_requires_source_grounded_problem_answer_cta_and_separate_brand_outro():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "MANDATORY STORY DESIGN" in source
    assert "First sentence names a concrete risk" in source
    assert "Give a real, useful answer immediately" in source
    assert "strong, specific CTA tied to THIS issue" in source
    assert "Do not put the slogan inside the main script or generate another outro." in source
    assert "original full-screen logo" in source
    assert "خليك فاكر دايما ... اسأل محمود" in source


def test_deterministic_reel_fallback_uses_reviewed_post_and_bounded_script():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "def deterministic_brief(topic: str, post: str)" in source
    assert "sentences = [part.strip() for part in re.split" in source
    assert "answer_source = \" \".join(sentences[:2])" in source
    assert "answer_words = answer_source.split()" in source
    assert "cta = \"اكتب سؤالك المحدد في التعليقات" in source
    assert "_bound_reel_script(script, max_words=75)" in source
    assert "Deterministic Reel script is too short" in source
