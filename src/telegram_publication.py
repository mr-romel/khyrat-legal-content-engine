from __future__ import annotations

import re

from telegram_bot import configured, send_message


def build_reels_prompt(*, topic: str, post: str) -> str:
    return f"""أنشئ Reels قانوني 9:16 عن الموضوع التالي اعتمادًا على المحتوى المعتمد فقط.
الموضوع: {topic}
المحتوى: {post}

45–75 ثانية، مصري طبيعي، Hook ثم شرح بسيط ثم خلاصة وCTA. لا تضف مادة أو حكمًا أو عقوبة أو ميعادًا أو استثناءً غير موجود. اقترح لقطات بسيطة ونصوص شاشة قصيرة. بدون موسيقى أو إعلان مباشر. حافظ على هوية «اسأل محمود»."""


def _source_links(value: str) -> list[str]:
    links = re.findall(r"https?://[^\s<>\]\)\"']+", str(value or ""))
    cleaned = [link.rstrip(".,؛،") for link in links]
    return list(dict.fromkeys(cleaned))[:8]


def send_single_publication_message(*, topic: str, post: str, status_text: str = "", legal_sources: str = "") -> None:
    """Send one compact Telegram package with the approved post, prompt and source links."""
    if not configured():
        print("Telegram not configured; publication package skipped.")
        return

    prompt = build_reels_prompt(topic=topic, post=post)
    text = f"🎬 KHYRAT LEGAL CONTENT ENGINE\n\n📌 الموضوع: {topic}\n\n🎥 PROMPT — GEMINI NOTEBOOK\n━━━━━━━━━━━━━━━━━━\n{prompt}"
    links = _source_links(legal_sources)
    if links:
        text += "\n\n🔗 المصادر القانونية:\n" + "\n".join(links)
    if status_text:
        text += f"\n\n📊 الحالة: {status_text}"

    if len(text) <= 4000:
        send_message(text)
        return

    print(f"Telegram publication package is long ({len(text)} chars); sending in safe chunks.")
    for start in range(0, len(text), 3900):
        send_message(text[start:start + 3900])


def send_single_status_message(*, text: str) -> None:
    if not configured():
        print("Telegram not configured; status notification skipped.")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…"
    send_message(text)
