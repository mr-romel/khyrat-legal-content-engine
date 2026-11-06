from __future__ import annotations

import hashlib
import random
from urllib.parse import urlparse


BLOGGER_HOST = "askmahmoudkhyrat.blogspot.com"


def valid_blogger_article_url(value: str) -> bool:
    url = str(value or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == BLOGGER_HOST
        and parsed.path not in {"", "/"}
        and not parsed.username
        and not parsed.password
    )


def build_video_comment_bundle(
    *,
    topic: str,
    article_url: str,
    video_id: str,
    platform: str,
) -> list[str]:
    """Build a stable 3-5 comment bundle with Q&A and a mandatory matching-article CTA.

    The bundle is randomized per video/platform but deterministic across retries,
    so an interrupted publishing job can resume without changing comment order.
    """
    if not valid_blogger_article_url(article_url):
        raise ValueError("A published, topic-matched Blogger article URL is required.")
    topic = " ".join(str(topic or "").split()).strip() or "الموضوع القانوني في الفيديو"
    topic = topic[:140]
    platform = str(platform or "").strip().lower()
    if platform not in {"facebook", "youtube"}:
        raise ValueError("platform must be facebook or youtube")
    seed = int(hashlib.sha256(f"{video_id}|{platform}".encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    count = rng.randint(3, 5)

    if platform == "facebook":
        question = f"سؤال مهم بخصوص {topic}: إيه أول مستند أو تفصيلة لازم نراجعها قبل اتخاذ أي إجراء؟"
        answer = (
            "الإجابة بتتحدد حسب تفاصيل الواقعة والمستندات والمواعيد المرتبطة بيها، "
            "وعشان كده لازم نفهم الحالة كاملة قبل تعميم أي حكم قانوني"
        )
        article_cta = f"📖 الشرح الكامل لنفس موضوع الفيديو والخطوات القانونية هنا:\n{article_url}"
        extra_ctas = [
            "لو عندك موقف مشابه، ابعت تفاصيله بشكل مختصر علشان نوضح لك الإطار القانوني المناسب",
            "اكتب سؤالك المحدد في التعليقات، وهنوضح النقطة القانونية في حدود المعلومات المتاحة",
        ]
        extra_questions = [
            "هل واجهتك نقطة مشابهة في الموضوع ده؟ اكتب استفسارك من غير نشر أي بيانات شخصية أو مستندات خاصة",
            "إيه الإجراء اللي شايف إنه محتاج شرح أكتر في الموضوع؟",
        ]
    else:
        question = f"سؤال للمراجعة: في موضوع {topic}، إيه المستند أو الواقعة اللي ممكن تغيّر التقييم القانوني؟"
        answer = (
            "مفيش إجابة واحدة تنطبق على كل الوقائع؛ التقييم بيتوقف على المستندات والتواريخ "
            "والتفاصيل الفعلية، ودي نقطة مهمة قبل اتخاذ أي خطوة"
        )
        article_cta = f"اقرأ المقال المرتبط بنفس موضوع الـShort، بالتفصيل والخطوات العملية:\n{article_url}"
        extra_ctas = [
            "لو محتاج توضيحًا لحالة مشابهة، اكتب سؤالك المحدد مع تجنب مشاركة بيانات شخصية",
            "تابع القناة للمزيد من الشروحات القانونية العملية، واحتفظ بالمقال للرجوع إليه",
        ]
        extra_questions = [
            "أي جزء من الموضوع يحتاج مثالًا عمليًا إضافيًا؟",
            "ما المستند الذي تبدأ بمراجعته في الحالة التي يناقشها الفيديو؟",
        ]

    # Three mandatory roles: a real topic-linked question, a cautious answer, and the exact article CTA.
    optional = [rng.choice(extra_ctas), rng.choice(extra_questions)]
    rng.shuffle(optional)
    comments = [article_cta, question, answer, *optional[: max(0, count - 3)]]
    # Vary order without losing the mandatory article link or the Q&A pair.
    fixed = comments[:3]
    rng.shuffle(fixed)
    return fixed + comments[3:]


def parse_published_comment_ids(value: str) -> list[str]:
    import json
    try:
        data = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]
