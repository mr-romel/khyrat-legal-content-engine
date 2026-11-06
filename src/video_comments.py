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

    topic_lower = topic.lower()
    is_secret_threat = any(term in topic_lower for term in (
        "تهديد", "إفشاء", "افشاء", "أسرار", "اسرار", "ابتزاز", "نشر معلومات خاصة"
    ))

    # Never publish the Google Sheets editorial title/angle. Public comments are
    # standalone legal prompts; only the legal subject is used for classification.
    if is_secret_threat:
        if platform == "facebook":
            questions = [
                "في واقعة التهديد بإفشاء أسرار، ما الدليل المتاح على صدور التهديد وتاريخه ونسبته إلى صاحبه؟",
                "ما الذي ينبغي التحقق منه أولًا: مضمون التهديد، أم وسيلة إرساله، أم توقيته؟",
                "هل توجد رسائل أو تسجيلات أو شهود يمكن أن يثبتوا واقعة التهديد وسياقها؟",
            ]
            answers = [
                "التقييم القانوني يبدأ بفحص مضمون التهديد وسياقه، والتحقق من الدليل ونسبته وتاريخه؛ فمجرد وجود خلاف لا يكفي وحده لإثبات الواقعة.",
                "العبرة بما يثبت صدور التهديد ومضمونه والظروف المحيطة به، ومدى توافر الأركان القانونية، لا بمجرد وصف الخلاف.",
                "يجب حفظ الدليل الأصلي وبياناته وتوقيتاته دون تعديل، ثم مراجعة الوقائع كاملة قبل تحديد الوصف القانوني أو الإجراء المناسب.",
            ]
        else:
            questions = [
                "في واقعة التهديد بإفشاء أسرار، ما الدليل الذي يثبت صدور التهديد وتاريخه ونسبته إلى صاحبه؟",
                "ما العناصر التي يجب التحقق منها قبل تحديد الوصف القانوني لواقعة التهديد؟",
                "كيف يؤثر مضمون الرسالة وسياقها وتوقيت إرسالها في التقييم القانوني؟",
            ]
            answers = [
                "يتطلب التقييم فحص مضمون التهديد وسياقه، والتحقق من الدليل ونسبته وتاريخه؛ ولا يكفي مجرد وجود خلاف لإثبات الواقعة.",
                "يتوقف التكييف القانوني على مضمون الفعل وطبيعته والدليل المتاح والظروف المحيطة به ومدى توافر الأركان القانونية.",
                "الأصل هو الاحتفاظ بالدليل الإلكتروني بصورته الأصلية وبياناته الزمنية، ثم فحصه مع باقي الوقائع قبل اختيار الإجراء.",
            ]
    else:
        questions = [
            "ما الواقعة أو المستند الحاسم الذي ينبغي التحقق منه قبل تحديد الإجراء القانوني؟",
            "ما التفصيلة التي قد تغيّر التقييم القانوني في الحالة التي يناقشها الفيديو؟",
            "ما أول معلومة يجب التأكد منها قبل اتخاذ خطوة في هذه الحالة؟",
        ]
        answers = [
            "التقييم القانوني يتوقف على الوقائع الثابتة والمستندات والتواريخ ذات الصلة، وليس على وصف المشكلة أو عنوانها وحده.",
            "اختيار الإجراء الصحيح يبدأ بتحديد الوقائع والتحقق من المستندات والمواعيد، ثم تطبيق القاعدة القانونية على الحالة.",
            "لا يصح تعميم نتيجة واحدة على جميع الحالات؛ فقد يغيّر اختلاف واقعة جوهرية أو مستند التكييف والإجراء.",
        ]

    if platform == "facebook":
        article_ctas = [
            f"للاطلاع على الشرح القانوني الكامل والتفاصيل العملية، راجع المقال المرتبط بالفيديو:\n{article_url}",
            f"يمكنك مراجعة المقال المتخصص المرتبط بموضوع الفيديو من هنا:\n{article_url}",
        ]
        extra_ctas = [
            "لطرح استفسار عام مرتبط بالموضوع، اكتب سؤالك دون نشر أسماء أو بيانات أو مستندات خاصة.",
            "إذا كانت لديك واقعة مشابهة، فاذكر طبيعتها بإيجاز مع تجنب مشاركة أي بيانات شخصية.",
        ]
        extra_questions = [
            "أي عنصر من عناصر الواقعة يحتاج إلى توضيح قانوني إضافي؟",
            "هل تحتاج إلى مثال عملي يوضح كيفية تقييم الدليل في هذه الحالة؟",
        ]
    else:
        article_ctas = [
            f"للتفاصيل القانونية والخطوات العملية، اقرأ المقال المرتبط بهذا الفيديو:\n{article_url}",
            f"الشرح الكامل للموضوع متاح في المقال التالي:\n{article_url}",
        ]
        extra_ctas = [
            "للاستفسارات العامة، اكتب سؤالك المحدد مع عدم نشر بيانات شخصية أو مستندات خاصة.",
            "اشترك لمتابعة الشروحات القانونية العملية، واحتفظ بالمقال للرجوع إليه.",
        ]
        extra_questions = [
            "أي عنصر من عناصر الواقعة يحتاج إلى توضيح إضافي؟",
            "ما الدليل أو المستند الذي ترى ضرورة شرحه بمثال عملي؟",
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
