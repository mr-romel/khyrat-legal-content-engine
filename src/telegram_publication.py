from __future__ import annotations

from telegram_bot import configured, send_message


def build_reels_prompt(*, topic: str, post: str) -> str:
    return f"""أنشئ فيديو Reels قانوني احترافي عن الموضوع التالي، اعتمادًا على المحتوى المعتمد فقط.

الموضوع: {topic}

المحتوى القانوني المعتمد:
{post}

التعليمات:
- فيديو رأسي 9:16، مدة 45–75 ثانية، مناسب للموبايل.
- باللهجة المصرية الطبيعية، بأسلوب محامٍ مصري هادئ وواثق ومهني.
- Hook قوي في البداية، ثم شرح مبسط للقاعدة القانونية، ثم خلاصة عملية أو CTA طبيعي.
- لا تغيّر النتيجة القانونية، ولا تضف مادة أو حكمًا أو عقوبة أو ميعادًا أو استثناءً أو واقعة غير موجودة في المحتوى.
- اقترح لقطات بصرية بسيطة ونصوصًا قصيرة على الشاشة لأهم النقاط فقط.
- بدون موسيقى أو مؤثرات تغطي الصوت، وبدون تحويل الفيديو لإعلان مباشر.
- حافظ على هوية «اسأل محمود» المهنية.

أخرج فيديو Reels جاهزًا للنشر، وليس مجرد نص مقترح."""


def send_single_publication_message(*, topic: str, post: str, status_text: str = "") -> None:
    """Send one compact Telegram package; the approved post appears only once, inside the prompt."""
    if not configured():
        print("Telegram not configured; publication package skipped.")
        return

    prompt = build_reels_prompt(topic=topic, post=post)
    text = (
        "🎬 KHYRAT LEGAL CONTENT ENGINE\n\n"
        f"📌 الموضوع: {topic}\n\n"
        "🎥 PROMPT — GEMINI NOTEBOOK\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{prompt}"
    )
    if status_text:
        text += f"\n\n📊 الحالة: {status_text}"

    # Telegram hard limit is 4096 characters. If an unusually long approved
    # post still pushes the compact prompt over the limit, split it safely into
    # consecutive chunks rather than failing the publication pipeline.
    if len(text) <= 4000:
        send_message(text)
        return

    print(f"Telegram publication package is long ({len(text)} chars); sending in safe chunks.")
    chunk_size = 3900
    for start in range(0, len(text), chunk_size):
        send_message(text[start:start + chunk_size])


def send_single_status_message(*, text: str) -> None:
    if not configured():
        print("Telegram not configured; status notification skipped.")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…"
    send_message(text)
