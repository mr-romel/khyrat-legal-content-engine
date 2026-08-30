from __future__ import annotations

import re

from telegram_bot import configured, send_message


def build_reels_prompt(*, topic: str, post: str) -> str:
    """Compact, copy-ready video prompt; keep the approved post as the sole legal source."""
    return (
        "أنشئ Reel قانوني 9:16 مدته 45–75 ثانية اعتمادًا فقط على المنشور المعتمد أدناه.\n"
        "مصري طبيعي، Hook قوي ثم شرح بسيط ثم خلاصة/CTA. حافظ على المعنى القانوني حرفيًا، "
        "ولا تضف مادة أو حكمًا أو عقوبة أو ميعادًا أو استثناءً أو واقعة غير موجودة. "
        "اقترح لقطات بسيطة ونصوص شاشة قصيرة، بدون موسيقى أو إعلان مباشر، وبهوية «اسأل محمود».\n\n"
        f"الموضوع: {topic}\n"
        f"المنشور المعتمد:\n{post.strip()}"
    )


def _source_links(value: str) -> list[str]:
    links = re.findall(r"https?://[^\s<>\]\)\"']+", str(value or ""))
    cleaned = [link.rstrip(".,؛،") for link in links]
    return list(dict.fromkeys(cleaned))[:6]


def send_single_publication_message(*, topic: str, post: str, status_text: str = "", legal_sources: str = "") -> None:
    """Send exactly one compact Telegram publication package."""
    if not configured():
        print("Telegram not configured; publication package skipped.")
        return

    prompt = build_reels_prompt(topic=topic, post=post)
    text = (
        "🎬 KHYRAT LEGAL CONTENT ENGINE\n"
        f"📌 {topic}\n\n"
        "🎥 PROMPT — GEMINI NOTEBOOK\n"
        f"{prompt}"
    )
    links = _source_links(legal_sources)
    if links:
        text += "\n\n🔗 المصادر القانونية:\n" + "\n".join(links)
    if status_text:
        text += f"\n\n📊 {status_text}"

    # Telegram allows 4096 chars. Keep the whole package in one message.
    # If an unusually long approved post would exceed the limit, shorten only
    # the copied source text so we never split the package into multiple messages.
    if len(text) > 4096:
        compact_post = post.strip()
        prompt_prefix = (
            "أنشئ Reel قانوني 9:16 مدته 45–75 ثانية اعتمادًا فقط على المنشور المعتمد. "
            "مصري طبيعي، Hook ثم شرح بسيط ثم خلاصة/CTA. لا تضف أي معلومة قانونية غير موجودة، "
            "وحافظ على هوية «اسأل محمود».\n\n"
            f"الموضوع: {topic}\nالمنشور المعتمد:\n"
        )
        fixed = len("🎬 KHYRAT LEGAL CONTENT ENGINE\n📌 \n\n🎥 PROMPT — GEMINI NOTEBOOK\n")
        source_block = len("\n\n🔗 المصادر القانونية:\n") + sum(len(x) + 1 for x in links)
        status_block = len(f"\n\n📊 {status_text}") if status_text else 0
        available = max(500, 4096 - fixed - len(prompt_prefix) - source_block - status_block - 20)
        compact_post = compact_post[:available].rstrip() + "…"
        prompt = prompt_prefix + compact_post
        text = "🎬 KHYRAT LEGAL CONTENT ENGINE\n📌 " + topic + "\n\n🎥 PROMPT — GEMINI NOTEBOOK\n" + prompt
        if links:
            text += "\n\n🔗 المصادر القانونية:\n" + "\n".join(links)
        if status_text:
            text += f"\n\n📊 {status_text}"

    send_message(text)


def send_single_status_message(*, text: str) -> None:
    if not configured():
        print("Telegram not configured; status notification skipped.")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…"
    send_message(text)
