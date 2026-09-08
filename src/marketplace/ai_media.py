"""Gemini helpers for Marketplace offers and Khamsat cover images."""
from __future__ import annotations

import base64
import io
import os
import re
from typing import Any

import requests
from PIL import Image

IMAGE_MODEL = "gemini-3.1-flash-image"
TEXT_MODEL = "gemini-3.8-flash"
KHAMSAT_SIZE = (1700, 970)


def _key() -> str:
    value = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not value:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط في Vercel")
    return value


def normalize_offer_price(value: Any, default: int = 5) -> int:
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        amount = default
    return max(5, (amount // 5) * 5)


def _budget_from_text(text: str) -> int | None:
    patterns = (
        r"(?:\$\s*|USD\s*|دولار(?:\s*أمريكي)?\s*)(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*(?:\$|USD|دولار)",
    )
    values: list[int] = []
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.IGNORECASE):
            amount = int(float(raw))
            if amount >= 5:
                values.append(amount)
    return min(values) if values else None


def offer_terms(opportunity: dict[str, Any]) -> tuple[int, int]:
    description = str(opportunity.get("description", ""))
    budget = _budget_from_text(description)
    requested = opportunity.get("suggested_price_usd", budget or 5)
    price = normalize_offer_price(requested, budget or 5)
    if budget is not None:
        price = min(price, normalize_offer_price(budget))
    days = max(1, int(opportunity.get("suggested_days", 3) or 3))
    return price, days


def _client():
    from google import genai
    return genai.Client(api_key=_key())


def _interaction_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for step in getattr(response, "steps", []) or []:
        if getattr(step, "type", "") != "model_output":
            continue
        for content in getattr(step, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                return str(text).strip()
    output = getattr(response, "output", None)
    if isinstance(output, str):
        return output.strip()
    return ""


def generate_offer(opportunity: dict[str, Any]) -> str:
    """Generate a project-specific Mostaql offer with enforced price rules."""
    title = str(opportunity.get("title", "")).strip()
    description = str(opportunity.get("description", "")).strip()
    price, days = offer_terms(opportunity)
    prompt = f"""
اكتب عرضًا احترافيًا على منصة مستقل لهذا المشروع تحديدًا، بعد قراءة العنوان والوصف
وكل الشروط والأسئلة الواردة فيه. مقدم العرض مستشار قانوني مصري متخصص في العقود
والشركات والعمل والقانون التجاري.

العنوان: {title}
الوصف والشروط والأسئلة:
{description}

قيود لا يجوز تغييرها:
- قيمة العرض النهائية: ${price} دولار أمريكي.
- السعر يجب أن يكون 5$ أو مضاعفًا لـ5 فقط، ولا تذكر سعرًا آخر.
- مدة التنفيذ: {days} أيام، ولا تقترح مدة تناقض شرط صاحب المشروع.

اكتب نصًا طبيعيًا بين 130 و220 كلمة. ابدأ بفهم المطلوب، واذكر متطلبين محددين من
المشروع، ثم وضّح طريقة التنفيذ والتسليم والمدة والقيمة. التزم حرفيًا بأي شروط أو
أسئلة أو صيغة طلبها صاحب المشروع. لا تكرر الوصف كاملًا.
ممنوع ذكر الهاتف أو البريد أو واتساب أو أي وسيلة تواصل خارج مستقل، وممنوع الدفع
خارج المنصة أو الروابط التسويقية. لا تدّعِ خبرات أو أعمالًا لم تُذكر. إذا كان هناك
نقص جوهري يمنع التنفيذ، اسأل سؤالًا واحدًا فقط في النهاية.
لا تستخدم عنوانًا للعرض، ولا Markdown، ولا مقدمات محفوظة، واكتب العرض فقط.
"""
    try:
        response = _client().interactions.create(model=TEXT_MODEL, input=prompt)
    except Exception as exc:
        raise RuntimeError(f"تعذر توليد عرض Gemini: {exc}") from exc
    text = _interaction_text(response)
    if not text:
        raise RuntimeError("Gemini لم يُرجع عرضًا نصيًا")
    return text


def _inline_bytes(response) -> bytes | None:
    for part in getattr(response, "parts", []) or []:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None) if inline else None
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return base64.b64decode(data)
    return None


def _interaction_image_bytes(response: Any) -> bytes | None:
    output_image = getattr(response, "output_image", None)
    data = getattr(output_image, "data", None) if output_image else None
    if isinstance(data, bytes):
        return data
    if isinstance(data, str) and data:
        return base64.b64decode(data)
    return None


def _rest_image(prompt: str, key: str) -> bytes:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "responseFormat": {"image": {"aspectRatio": "16:9"}},
        },
    }
    response = requests.post(
        url,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini لم يُرجع بيانات صورة")


def generate_khamsat_image(service: dict[str, Any]) -> bytes:
    """Generate and normalize a Khamsat cover to exactly 1700x970 JPEG."""
    key = _key()
    title = str(service.get("title", "خدمة قانونية")).strip() or "خدمة قانونية"
    prompt = f"""
أنشئ غلافًا احترافيًا لخدمة خمسات بعنوان: {title}
المجال: خدمات قانونية مصرية، عقود، شركات، استشارات ومراجعة قانونية.
تصميم عربي حديث وراقي وواضح على الهاتف، يعكس الثقة والمهنية. استخدم رموزًا قانونية
مجردة مثل عقد وملف وقلم وميزان عدالة. لا تستخدم أشخاصًا حقيقيين، ولا شعار خمسات أو
أي منصة، ولا أسعارًا أو بيانات غير موجودة في العنوان. ضع عنوان الخدمة فقط داخل
التصميم بخط عربي واضح مع مساحة أمان واسعة. نسبة الصورة 16:9.
"""
    raw: bytes | None = None
    try:
        response = _client().interactions.create(model=IMAGE_MODEL, input=prompt)
        raw = _interaction_image_bytes(response)
    except Exception:
        raw = None
    if not raw:
        try:
            from google.genai import types
            response = _client().models.generate_content(
                model=IMAGE_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    response_format={"image": {"aspect_ratio": "16:9"}},
                ),
            )
            raw = _inline_bytes(response)
        except Exception:
            raw = None
    if not raw:
        raw = _rest_image(prompt, key)

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    target_w, target_h = KHAMSAT_SIZE
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize(
        (max(target_w, round(image.width * scale)), max(target_h, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    final = resized.crop((left, top, left + target_w, top + target_h))
    output = io.BytesIO()
    final.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    return output.getvalue()


def image_data_url(image_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
