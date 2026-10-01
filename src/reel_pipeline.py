from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from google import genai
from config import load_config
from sheets import create_service, ensure_headers, get_values, row_to_dict, update_row
from telegram_bot import send_video
from free_media import cached_fallback_assets, fetch_openverse_images, fetch_wikimedia_images, generate_legal_cards

MPT_REPO = "https://github.com/harry0703/MoneyPrinterTurbo.git"
OUTPUT_ROOT = Path("generated/reels")


def choose_row(rows: list[dict[str, str]]) -> tuple[int, dict[str, str]] | None:
    candidates = []
    for number, row in enumerate(rows, start=2):
        if str(row.get("الحالة", "")).strip().upper() != "PUBLISHED":
            continue
        if str(row.get("Reel Status", "")).strip().upper() in {"GENERATING", "REVIEW", "APPROVED", "PUBLISHED"}:
            continue
        if str(row.get("المحتوى", "")).strip():
            candidates.append((number, row))
    return candidates[-1] if candidates else None


def make_brief(api_key: str, model: str, topic: str, post: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    prompt = (
        "Create one Arabic legal short-video package for an Egyptian lawyer brand. "
        "Use ONLY the supplied reviewed post and topic. Never invent legal facts. "
        "Natural professional Egyptian Arabic, spoken rhythm, no emojis, no sales pitch. "
        "Strong concrete hook, one practical legal point, useful ending, 45-70 seconds. "
        "Return JSON only with script, video_terms, facebook_caption, linkedin_caption, emotion_map. "
        "video_terms must be English stock-footage searches in chronological order. "
        "emotion_map must contain one item per meaningful sentence with sentence_index and delivery_emotion. "
        "Choose delivery emotions that fit the legal subject and sentence function, such as calm_authority, warning, empathy, urgency, reassurance, clarification, or strong_cta. "
        "The voice must sound like a confident Egyptian male lawyer in his late 30s: natural Egyptian Arabic, clear diction, measured pace, never a newsreader or generic MSA narrator. "
        "Use punctuation, sentence length, pauses, and wording to make the intended emotion audible without inventing legal facts.\n\n"
        "TOPIC:\n" + topic + "\n\nREVIEWED POST:\n" + post
    )
    primary = (model or "gemini-3.6-flash").strip()
    fallback = (os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash") or "").strip()
    models = [primary] + ([fallback] if fallback and fallback != primary else [])
    last_error = None
    response = None
    for selected_model in models:
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config={"response_mime_type": "application/json", "max_output_tokens": 5000},
            )
            break
        except Exception as exc:
            last_error = exc
            print(f"Reel Gemini model failed: {selected_model}: {exc}")
    if response is None:
        print(f"Gemini unavailable for Reel; using deterministic fallback: {last_error}")
        return deterministic_brief(topic, post)
    data = json.loads((response.text or "").strip())
    script = str(data.get("script", "")).strip()
    terms = data.get("video_terms") if isinstance(data.get("video_terms"), list) else []
    if len(script) < 350 or len(terms) < 4:
        raise RuntimeError("Reel package is incomplete.")
    return {
        "script": script,
        "video_terms": [str(x).strip() for x in terms[:8] if str(x).strip()],
        "facebook_caption": str(data.get("facebook_caption", "")).strip(),
        "linkedin_caption": str(data.get("linkedin_caption", "")).strip(),
        "emotion_map": data.get("emotion_map") if isinstance(data.get("emotion_map"), list) else [],
    }




def deterministic_brief(topic: str, post: str) -> dict[str, Any]:
    text = " ".join(str(post or "").split())
    parts = [p.strip() for p in text.replace("؟", "؟|").replace(".", ".|").split("|") if len(p.strip()) > 35]
    selected = parts[:6]
    body = " ".join(selected)
    if len(body) < 350:
        body = text[:1800]
    script = (
        f"خليني أوضح لك نقطة مهمة جدًا في موضوع {topic}. "
        f"{body} "
        "والأهم قبل ما تاخد أي خطوة إنك تراجع التفاصيل والمستندات المرتبطة بحالتك، لأن التطبيق القانوني بيختلف حسب الوقائع. "
        "لو الموضوع يخصك فعلًا، راجع النص القانوني والمستندات مع محاميك قبل اتخاذ قرار نهائي."
    )
    sentences = [x.strip() for x in script.replace("؟", "؟|").replace(".", ".|").split("|") if x.strip()]
    emotions = []
    for i, sentence in enumerate(sentences, start=1):
        emotion = "strong_cta" if i == len(sentences) else "calm_authority"
        if any(k in sentence for k in ("مهم", "قبل ما", "يختلف")):
            emotion = "warning"
        emotions.append({"sentence_index": i, "delivery_emotion": emotion})
    return {
        "script": script,
        "video_terms": [
            "Egyptian lawyer legal consultation",
            "legal documents paperwork",
            "contract signing close up",
            "law office discussion",
            "court legal files",
            "business legal meeting",
        ],
        "facebook_caption": f"معلومة قانونية مهمة عن {topic}. راجع التفاصيل قبل ما تاخد أي خطوة.",
        "linkedin_caption": f"Legal practical note: {topic}. Review the facts and documents before making a decision.",
        "emotion_map": emotions,
        "generation_mode": "deterministic_fallback",
    }



def main() -> int:
    cfg = load_config()
    service = create_service(cfg["service_account_info"])
    sheet_name = cfg["sheet_range"].split("!", 1)[0]
    ensure_headers(service, cfg["sheet_id"], sheet_name)
    values = get_values(service, cfg["sheet_id"], cfg["sheet_range"])
    selected = choose_row([row_to_dict(row) for row in values[1:]])
    if not selected:
        print("Reel generator: no eligible published content row.")
        return 0

    row_number, row = selected
    topic = str(row.get("الموضوع", "")).strip()
    post = str(row.get("المحتوى", "")).strip()
    output_dir = OUTPUT_ROOT / ("row_" + str(row_number))
    update_row(service, cfg["sheet_id"], sheet_name, row_number, {
        "Reel Status": "GENERATING",
        "Reel Approval": "",
        "Reel Last Error": "",
    })

    try:
        brief = make_brief(cfg["gemini_api_key"], os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), topic, post)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "script.txt").write_text(brief["script"], encoding="utf-8")
        (output_dir / "reel_plan.json").write_text(json.dumps({"topic": topic, **brief}, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "delivery_map.json").write_text(json.dumps(brief.get("emotion_map", []), ensure_ascii=False, indent=2), encoding="utf-8")

        scene_dir = output_dir / "scenes"
        scenes = fetch_openverse_images(brief["video_terms"], scene_dir)
        if len(scenes) < 4:
            needed = max(4, 8 - len(scenes))
            scenes.extend(fetch_wikimedia_images(brief["video_terms"], scene_dir, target=needed))
        if len(scenes) < 4:
            cached = cached_fallback_assets(OUTPUT_ROOT, scene_dir, limit=8)
            scenes.extend(cached)
        if len(scenes) < 4:
            scenes.extend(generate_legal_cards(scene_dir, topic, count=6))
        if len(scenes) < 4:
            raise RuntimeError("لم يتم العثور على عدد كافٍ من المواد المرخّصة مجانًا لهذا الريل.")
        source_file = scene_dir / "sources.json"
        sources = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else []
        attributions = []
        for source in sources:
            if str(source.get("license", "")).lower() == "by":
                title = source.get("title") or "Openverse media"
                creator = source.get("creator") or "unknown creator"
                url = source.get("source_url") or source.get("media_url") or ""
                attributions.append(f"{title} — {creator}" + (f" — {url}" if url else ""))
        if attributions:
            credit_text = "\n\nمصادر المواد البصرية (ترخيص Creative Commons Attribution):\n" + "\n".join(attributions)
            brief["facebook_caption"] = (brief["facebook_caption"] or brief["script"]) + credit_text
            brief["linkedin_caption"] = (brief["linkedin_caption"] or brief["script"]) + credit_text
        (output_dir / "media_sources.json").write_text(
            json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with tempfile.TemporaryDirectory(prefix="khyrat-mpt-") as temp:
            mpt = Path(temp) / "MoneyPrinterTurbo"
            subprocess.run(["git", "clone", "--depth", "1", MPT_REPO, str(mpt)], check=True, timeout=180)
            command = [
                "uv", "run", "--no-project", "--python", "3.11", "python", "docs/skill/mpt_agent.py",
                "--subject", topic,
                "--root", str(mpt),
                "--",
                "--video-script", brief["script"],
                "--video-terms", ", ".join(brief["video_terms"]),
                "--video-source", "local",
                "--video-materials", ",".join(str(p.resolve()) for p in scenes),
                "--video-aspect", "9:16",
                "--video-count", "1",
                "--video-clip-duration", "5",
                "--match-materials-to-script",
                "--voice-name", "ar-EG-ShakirNeural",
            "--voice-rate", "0.96",
                "--subtitle-enabled",
                "--subtitle-position", "bottom",
                "--subtitle-display-mode", "sentence",
                "--subtitle-animation", "none",
                "--font-size", "54",
                "--bgm-type", "random",
                "--bgm-volume", "0.15",
            ]
            env = os.environ.copy()
            result = subprocess.run(command, cwd=mpt, env=env, text=True, capture_output=True, timeout=1800, check=False)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout)[-6000:])
            video_line = [line for line in result.stdout.splitlines() if line.startswith("VIDEO_FILE=")]
            if not video_line:
                raise RuntimeError("MoneyPrinterTurbo returned no VIDEO_FILE.")
            video = Path(video_line[-1].split("=", 1)[1].strip())
            output_video = output_dir / "daily-reel.mp4"
            shutil.copy2(video, output_video)

        update_row(service, cfg["sheet_id"], sheet_name, row_number, {
            "Reel Status": "REVIEW",
            "Reel Script": brief["script"],
            "Reel File": str(output_dir / "daily-reel.mp4"),
            "Reel Run ID": os.getenv("GITHUB_RUN_ID", ""),
            "Reel Approval": "",
            "Reel Review": "جاهز للمراجعة اليدوية قبل أي نشر",
            "Reel Last Error": "",
        })
        video_path = output_dir / "daily-reel.mp4"
        try:
            send_video(
                str(video_path),
                caption=f"🎬 Reel للمراجعة — الصف {row_number}\n\nالموضوع: {topic}\n\nالصوت: رجل مصري، نبرة محامٍ واثق، مع خريطة مشاعر حسب الجمل",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "✅ اعتماد الريل", "callback_data": f"reel_approve:{row_number}"},
                        {"text": "❌ رفض الريل", "callback_data": f"reel_reject:{row_number}"},
                    ]]
                },
            )
        except Exception as notify_exc:
            print(f"Telegram Reel preview unavailable: {notify_exc}")
        print("REEL_READY row=" + str(row_number) + " file=" + str(video_path))
        return 0
    except Exception as exc:
        update_row(service, cfg["sheet_id"], sheet_name, row_number, {
            "Reel Status": "FAILED",
            "Reel Last Error": str(exc)[:1500],
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
