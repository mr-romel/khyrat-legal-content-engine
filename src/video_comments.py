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
        questions = [
            f"سؤال مهم بخصوص {topic}: إيه أول مستند أو تفصيلة لازم نراجعها قبل اتخاذ أي إجراء؟",
            f"سؤال عن {topic}: أنهي واقعة أو تاريخ ممكن يغيّر التقييم القانوني؟",
            f"سؤال عن {topic}: إيه أول خطوة عملية المفروض تتراجع قبل أي تصرف؟",
        ]
        answers = [
            "الإجابة بتتحدد حسب تفاصيل الواقعة والمستندات والمواعيد المرتبطة بيها، وعشان كده لازم نفهم الحالة كاملة قبل تعميم أي حكم قانوني",
            "الإجابة مش واحدة في كل الحالات؛ لازم نراجع المستندات والتواريخ وتسلسل الأحداث قبل تحديد الإجراء المناسب",
            "الإجابة العملية بتبدأ بتجميع المستندات وفهم الوقائع، لأن تفصيلة صغيرة ممكن تغيّر التقييم من حالة للتانية",
        ]
        article_ctas = [
            f"📖 المقال الكامل المرتبط بنفس موضوع الفيديو، مع التفاصيل والخطوات العملية:\n{article_url}",
            f"للي عايز يرجع للشرح بالتفصيل: ده رابط مقالنا عن نفس موضوع الفيديو:\n{article_url}",
            f"التفاصيل القانونية والأمثلة العملية في المقال المرتبط بالفيديو هنا:\n{article_url}",
        ]
        extra_ctas = [
            "لو عندك موقف مشابه، ابعت تفاصيله بشكل مختصر علشان نوضح لك الإطار القانوني المناسب",
            "لو محتاج توضيحًا لحالة مشابهة، ابعت استفسارك مع تجنب مشاركة بيانات أو مستندات خاصة",
            "تقدر تبعت سؤالك المحدد علشان نوضح لك النقاط اللي محتاجة مراجعة في حالتك",
        ]
        extra_questions = [
            "هل واجهتك نقطة مشابهة في الموضوع ده؟ اكتب استفسارك من غير نشر أي بيانات شخصية أو مستندات خاصة",
            "إيه الإجراء اللي شايف إنه محتاج شرح أكتر في الموضوع؟",
            "أنهي نقطة تحب نشوفها في مثال عملي منفصل؟",
        ]
    else:
        questions = [
            f"سؤال للمراجعة: في موضوع {topic}، إيه المستند أو الواقعة اللي ممكن تغيّر التقييم القانوني؟",
            f"سؤال عن {topic}: ما التفصيلة التي يجب التحقق منها قبل اختيار الإجراء القانوني؟",
            f"سؤال عن {topic}: ما أول معلومة لازم تتأكد منها؟",
        ]
        answers = [
            "مفيش إجابة واحدة تنطبق على كل الوقائع؛ التقييم بيتوقف على المستندات والتواريخ والتفاصيل الفعلية، ودي نقطة مهمة قبل اتخاذ أي خطوة",
            "الإجابة القانونية محتاجة مراجعة الوقائع والمستندات والمواعيد، مش الاعتماد على عنوان المشكلة وحده",
            "الإجابة بتتحدد بعد فهم تفاصيل الحالة ومراجعة الأدلة المتاحة، لأن اختلاف الوقائع ممكن يغيّر النتيجة",
        ]
        article_ctas = [
            f"اقرأ المقال المرتبط بنفس موضوع الـShort، بالتفصيل والخطوات العملية:\n{article_url}",
            f"المقال الكامل الذي يشرح موضوع الفيديو موجود هنا:\n{article_url}",
            f"للمراجعة والتفاصيل القانونية المرتبطة بهذا الـShort:\n{article_url}",
        ]
        extra_ctas = [
            "لو محتاج توضيحًا لحالة مشابهة، اكتب سؤالك المحدد مع تجنب مشاركة بيانات شخصية",
            "تابع القناة للمزيد من الشروحات القانونية العملية، واحتفظ بالمقال للرجوع إليه",
            "اشترك لمتابعة الشروحات القانونية، وارجع للمقال المرتبط عند مراجعة التفاصيل",
        ]
        extra_questions = [
            "أي جزء من الموضوع يحتاج مثالًا عمليًا إضافيًا؟",
            "ما المستند الذي تبدأ بمراجعته في الحالة التي يناقشها الفيديو؟",
            "ما النقطة التي تحتاج إلى توضيح أكثر قبل اتخاذ قرار؟",
        ]

    question = rng.choice(questions)
    answer = rng.choice(answers)
    article_cta = rng.choice(article_ctas)

    # Keep the conversation readable: question, answer, then the mandatory article CTA.
    optional = [rng.choice(extra_ctas), rng.choice(extra_questions)]
    rng.shuffle(optional)
    return [question, answer, article_cta, *optional[: max(0, count - 3)]]


def parse_published_comment_ids(value: str) -> list[str]:
    import json
    try:
        data = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]
