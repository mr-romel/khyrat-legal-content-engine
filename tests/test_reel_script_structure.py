from pathlib import Path


def test_reel_prompt_requires_hook_question_answer_cta_and_separate_brand_outro():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "MANDATORY RETENTION STRUCTURE" in source
    assert "a very strong, shocking but truthful hook" in source
    assert "Immediately ask one short, direct question" in source
    assert "Answer that exact question clearly" in source
    assert "A natural, compelling CTA" in source
    assert "Do not put the slogan inside the main script or generate another outro." in source
    assert 'rtl("خليك فاكر دايمًا")' in source
    assert 'rtl("اسأل محمود")' in source


def test_deterministic_reel_fallback_uses_hook_question_answer_action_cta_order():
    source = (Path(__file__).resolve().parents[1] / "src" / "reel_pipeline.py").read_text(encoding="utf-8")
    assert "hook_options = [" in source
    assert 'question = "طيب، إيه السؤال اللي لازم تجاوب عليه قبل ما تتحرك؟"' in source
    assert "answer = (" in source
    assert "action = (" in source
    assert "cta = " in source
    assert 'script = " ".join([hook_options[hook_index], question, answer, action, cta])' in source
