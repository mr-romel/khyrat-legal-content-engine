import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from repair_recent_blogger_images import _replace_hero


def test_replaces_exactly_the_first_hero_image_and_preserves_article_body():
    original = '<article><figure><img src="old.jpg" alt="old"></figure><p>Legal body remains.</p><figure><img src="second.jpg"></figure></article>'
    updated = _replace_hero(original, "https://blogger.googleusercontent.com/new.jpg", "عنوان المقال")
    assert updated.count('src="https://blogger.googleusercontent.com/new.jpg"') == 1
    assert 'src="old.jpg"' not in updated
    assert 'src="second.jpg"' in updated
    assert "Legal body remains." in updated


def test_adds_hero_when_article_has_no_images():
    updated = _replace_hero("<article><p>Article text.</p></article>", "https://example.com/new.jpg", "عنوان")
    assert updated.index("<figure>") < updated.index("Article text.")
    assert 'alt="عنوان"' in updated


def test_does_not_mutate_source_string():
    original = '<article><img src="old.jpg"></article>'
    _replace_hero(original, "https://example.com/new.jpg", "عنوان")
    assert 'src="old.jpg"' in original


def test_scene_query_uses_topic_specific_visual_terms_for_recent_legal_posts():
    from repair_recent_blogger_images import _scene_query
    assert "customs" in _scene_query("إجراءات التحفظ على المضبوطات ومخاطر التوقيع على محضر الضبط في مصر")
    assert "shipping containers" in _scene_query("أثر اللائحة التنفيذية لقانون الجمارك والقرارات الوزارية على المستوردين والشركات في مصر")
    assert "calendar deadline" in _scene_query("كيفية حساب ميعاد دعوى إلغاء القرار الإداري أمام مجلس الدولة")
