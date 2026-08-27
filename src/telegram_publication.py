from __future__ import annotations

from telegram_bot import configured, send_message


def build_reels_prompt(*, topic: str, post: str) -> str:
    return f"""أنتج فيديو Reels قانوني احترافي عن نفس الموضوع التالي، اعتمادًا على المحتوى المرفق فقط.

الموضوع:
{topic}

المحتوى القانوني المعتمد:
{post}

التعليمات الإلزامية:
1) الفيديو رأسي 9:16 ومصمم للعرض على شاشة الهاتف المحمول.
2) اللغة العربية المصرية العامية المفهومة والطبيعية، مع الحفاظ الكامل على المعنى القانوني الصحيح دون اختراع أي معلومة أو إضافة قاعدة قانونية غير موجودة في المحتوى المعتمد.
3) مدة مناسبة لـReels، ويفضل 45–75 ثانية حسب كثافة الموضوع، بدون إطالة أو حشو.
4) الأداء بصوت محامٍ ذكر مصري الجنسية في أواخر الثلاثينات، صوته واضح وهادئ وواثق، وإلقاؤه مهني ومطمئن ويدعو للثقة دون مبالغة أو تمثيل مصطنع.
5) يبدأ الفيديو بـHook قوي وواضح خلال الثواني الأولى، ثم يشرح المشكلة والقاعدة القانونية ببساطة، ثم ينتهي بخلاصة عملية أو دعوة طبيعية للتفاعل.
6) لا تستخدم لغة فصحى ثقيلة ولا مصطلحات قانونية غير ضرورية. إذا كان المصطلح القانوني ضروريًا، اشرحه ببساطة.
7) لا تجعل الفيديو يبدو كمحاضرة أو مذكرة قانونية؛ المطلوب محتوى سريع، إنساني، جذاب وسهل الفهم.
8) اقترح مشاهد ولقطات بصرية مناسبة للموضوع، مع انتقالات بسيطة وسريعة، وتجنب الزحام البصري.
9) أضف نصوصًا قصيرة على الشاشة متزامنة مع أهم النقاط، كبيرة وواضحة على الهاتف، بدون نسخ الكلام كاملًا على الشاشة.
10) لا تستخدم موسيقى أو مؤثرات صوتية تغطي على صوت المحامي، واجعل الصوت هو العنصر الأساسي.
11) حافظ على هوية «اسأل محمود» المهنية، بدون إدخال أسماء أو معلومات شخصية غير موجودة في المحتوى.
12) ممنوع تغيير النتيجة القانونية أو تبسيطها بطريقة تؤدي إلى خطأ قانوني.
13) ممنوع اختراع مادة قانونية أو رقم حكم أو عقوبة أو ميعاد أو استثناء أو واقعة غير واردة في المحتوى المعتمد.
14) لا تحول الفيديو إلى إعلان مباشر؛ الأولوية للقيمة القانونية والثقة.

أخرج فيديو Reels جاهزًا للنشر، وليس مجرد نص مقترح، مع تطبيق جميع التعليمات السابقة حرفيًا."""


def send_single_publication_message(*, topic: str, post: str, status_text: str = "") -> None:
    """Send a compact Telegram package: the approved post appears only inside the Reels prompt."""
    if not configured():
        print("Telegram not configured; publication package skipped.")
        return

    # The approved post is already included once inside the prompt. Do not print
    # it separately, which previously duplicated a long post and could exceed
    # Telegram's 4096-character single-message limit.
    prompt = build_reels_prompt(topic=topic, post=post)
    text = (
        "🎬 KHYRAT LEGAL CONTENT ENGINE — CONTENT PACKAGE\n\n"
        f"📌 الموضوع: {topic}\n\n"
        "🎥 PROMPT — GEMINI NOTEBOOK\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{prompt}"
    )
    if status_text:
        text += f"\n\n━━━━━━━━━━━━━━━━━━\n📊 الحالة: {status_text}"

    # Keep a safety margin below Telegram's hard 4096-character limit.
    if len(text) > 4000:
        raise RuntimeError(
            f"Telegram publication package is too long ({len(text)} characters) even after removing duplicate post text."
        )
    send_message(text)


def send_single_status_message(*, text: str) -> None:
    if not configured():
        print("Telegram not configured; status notification skipped.")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…"
    send_message(text)
