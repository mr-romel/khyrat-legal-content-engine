from pathlib import Path


def test_reel_prompt_requires_concrete_problem_answer_cta_and_separate_brand_outro():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "MANDATORY STORY DESIGN" in source
    assert "First sentence names a concrete risk" in source
    assert "direct answer immediately" in source
    assert "strong, specific CTA tied to THIS issue" in source
    assert "Do not put the slogan inside the main script or generate another outro." in source
    assert 'rtl("خليك فاكر دايمًا")' in source
    assert 'rtl("اسأل محمود")' in source


def test_deterministic_reel_fallback_uses_problem_question_answer_action_cta_order():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "hook_options = [" in source
    assert 'question = "إمتى الاعتراف ممكن يفقد قيمته القانونية؟"' in source
    assert "answer = (" in source
    assert "action = (" in source
    assert "cta = " in source
    assert 'script = " ".join([hook_options[hook_index], question, answer, action, cta])' in source
