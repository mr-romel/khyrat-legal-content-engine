import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blogger_editor import SYSTEM_PROMPT


def test_blogger_editor_prioritizes_clickworthy_truthful_titles_and_snippets():
    prompt = SYSTEM_PROMPT.lower()
    assert "45-65 characters" in prompt
    assert "120-155 arabic characters" in prompt
    assert "without clickbait" in prompt
    assert "exact core search phrase near the beginning" in prompt
    assert "why this page is the best match" in prompt


def test_blogger_editor_rejects_generic_or_sensational_seo_copy():
    prompt = SYSTEM_PROMPT.lower()
    assert "sensational promises" in prompt
    assert "generic دليل عملي" in prompt
    assert "do not claim an outcome or urgency" in prompt
