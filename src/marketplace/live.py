"""Live Marketplace acquisition and AI helpers."""
from __future__ import annotations

import base64
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image

MOSTAQL_PROJECTS_URL = "https://mostaql.com/projects"
MOSTAQL_LEGAL_FEEDS = (
    "https://mostaql.com/projects/skill/legal",
    "https://mostaql.com/projects/skill/contracts",
    "https://mostaql.com/projects/skill/legal-writing",
    "https://r.jina.ai/https://mostaql.com/projects/skill/legal",
)
LEGAL_TERMS = {
    "عقد": 30, "عقود": 30, "اتفاقية": 30, "اتفاقيات": 30, "محامي": 35,
    "محاماة": 35, "قانون": 30, "قانوني": 30, "استشارة قانونية": 35,
    "صياغة": 25, "مراجعة": 25, "لائحة": 25, "شروط": 20, "شركة": 15,
    "شراكة": 25, "عمل": 15, "عمال": 20, "وظيفة": 10, "موارد بشرية": 20,
    "تجاري": 20, "تجارية": 20, "nda": 30, "non-disclosure": 30,
    "terms": 20, "privacy policy": 20, "legal": 30, "lawyer": 35,
    "contract": 30, "agreement": 30, "employment": 20, "compliance": 20,
    "governance": 20,
}


class _ProjectParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.meta: dict[str, str] = {}
        self._href = ""
        self._anchor_text: list[str] = []
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "meta":
            key = data.get("name") or data.get("property")
            value = data.get("content")
            if key and value:
                self.meta[key.lower()] = value.strip()
        elif tag == "a":
            href = data.get("href") or ""
            if "/project/" in href:
                self._href = href
                self._anchor_text = []
                self._in_anchor = True

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_anchor:
            title = " ".join("".join(self._anchor_text).split())
            if self._href and title:
                self.links.append((self._href, title))
            self._href = ""
            self._anchor_text = []
            self._in_anchor = False


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; KhyratMarketplace/2.2; +https://github.com/mr-romel/khyrat-legal-content-engine)",
        "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.7",
    })
    return s


def score_legal_relevance(title: str, description: str) -> tuple[int, list[str]]:
    text = f"{title} {description}".lower()
    hits = [(term, points) for term, points in LEGAL_TERMS.items() if term in text]
    score = min(100, sum(points for _, points in hits))
    reasons = [f"مطابقة قانونية: {term}" for term, _ in hits[:8]] or ["لا توجد مطابقة قانونية كافية"]
    return score, reasons


def _fetch_project_list(session: requests.Session, url: str, timeout: int = 12) -> list[tuple[str, str]]:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []
    parser = _ProjectParser()
    parser.feed(response.text)
    if parser.links:
        return parser.links
    markdown_links = re.findall(r"\[([^\]]+)\]\((https://mostaql\.com/project/\d+[^)]*)\)", response.text, flags=re.IGNORECASE)
    return [(href, " ".join(title.split())) for title, href in markdown_links]


def _detail(session: requests.Session, url: str) -> dict[str, str]:
    try:
        response = session.get(url, timeout=8)
        response.raise_for_status()
        parser = _ProjectParser()
        parser.feed(response.text)
        description = parser.meta.get("description") or parser.meta.get("og:description") or ""
        return {"description": description[:6000]}
    except requests.RequestException:
        reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://")
        try:
            response = session.get(reader_url, timeout=8)
            response.raise_for_status()
            return {"description": response.text[:6000]}
        except requests.RequestException:
            return {"description": ""}


def fetch_mostaql_projects(limit: int = 12, minimum_score: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 30))
    session = _session()
    unique: dict[str, str] = {}
    for feed_url in MOSTAQL_LEGAL_FEEDS:
        for href, title in _fetch_project_list(session, feed_url):
            url = urljoin(MOSTAQL_PROJECTS_URL, href)
            if re.search(r"/project/\d+", url):
                unique.setdefault(url, title)
            if len(unique) >= limit * 5:
                break
        if len(unique) >= limit * 5:
            break
    if not unique:
        for href, title in _fetch_project_list(session, MOSTAQL_PROJECTS_URL):
            url = urljoin(MOSTAQL_PROJECTS_URL, href)
            if re.search(r"/project/\d+", url):
                unique.setdefault(url, title)
            if len(unique) >= limit * 5:
                break
    candidates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_detail, session, url): (url, title) for url, title in list(unique.items())[:limit * 4]}
        for future in as_completed(futures):
            url, title = futures[future]
            detail = future.result()
            description = detail.get("description", "")
            score, reasons = score_legal_relevance(title, description)
            if score < minimum_score:
                continue
            candidates.append({"platform": "mostaql", "title": title, "description": description or title,
                               "source_url": url, "match_score": score, "rationale": reasons, "acquisition_score": score})
    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    return candidates[:limit]


def _gemini_client():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط في Vercel")
    from google import genai
    return genai.Client(api_key=key)


def normalize_offer_price(value: Any, default: int = 5) -> int:
    """Return a valid USD offer in 5-dollar increments without exceeding a stated budget."""
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        amount = default
    return max(5, (amount // 5) * 5)


def _budget_from_text(text: str) -> int | None:
    matches = re.findall(r"(?:\$|دولار(?:\s*أمريكي)?\s*)\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    values = [int(float(x)) for x in matches if float(x) >= 5]
    return min(values) if values else None


def offer_terms(opportunity: dict[str, Any]) -> tuple[int, int]:
    description = str(opportunity.get("description", ""))
    budget = _budget_from_text(description)
    requested = opportunity.get("suggested_price_usd", budget or 5)
    price = normalize_offer_price(requested, default=budget or 5)
    if budget is not None:
        price = min(price, normalize_offer_price(budget))
    days = max(1, int(opportunity.get("suggested_days", 3) or 3))
    return price, days


def generate_case_specific_offer(opportunity: dict[str, Any]) -> str:
    """Generate a case-specific Mostaql proposal that follows platform-safe rules."""
    client = _gemini_client()
    title = str(opportunity.get("title", "")).strip()
    description = str(opportunity.get("description", "")).strip()
    price, days = offer_terms(opportunity)
    prompt = f"""
أنت تكتب عرضًا احترافيًا حقيقيًا على منصة مستقل لمستشار قانوني مصري متخصص في
العقود والشركات والعمل والقانون التجاري. اكتب العرض لهذا المشروع تحديدًا بعد قراءة
كل التفاصيل والشروط والأسئلة الواردة فيه.

المشروع:
العنوان: {title}
الوصف الكامل: {description}

بيانات العرض الإلزامية:
- قيمة العرض: ${price} دولار أمريكي فقط.
- القيمة يجب أن تكون 5 دولار أو أحد مضاعفات 5، ولا تغيّرها.
- مدة التنفيذ المقترحة: {days} أيام، ولا تقترح مدة تناقض شرط صاحب المشروع.

قواعد مستقل:
- ابدأ بفهم المطلوب، ولا تستخدم افتتاحية محفوظة أو قالبًا عامًا.
- اذكر بوضوح نقطتين محددتين من متطلبات المشروع تثبتان أنك قرأته.
- بيّن ما سيتم تسليمه وكيف ستنفذ العمل، مع الالتزام بأي شروط أو أسئلة أو صيغة طلبها صاحب المشروع.
- لا تدّعِ خبرة أو عملاً سابقًا أو أدوات لم يذكرها المستخدم.
- لا تذكر أي وسيلة تواصل خارج مستقل، ولا بريدًا أو هاتفًا أو واتساب أو روابط تسويقية.
- لا تطلب الدفع خارج المنصة، ولا تعد بنتيجة تخالف قوانين المنصة.
- لا تقل إنك وافقت على شرط لم تفهمه؛ إذا كان هناك نقص جوهري، اسأل سؤالًا واحدًا فقط في النهاية.
- اجعل النص بين 130 و220 كلمة تقريبًا، عربيًا طبيعيًا ومهنيًا وغير متكلف.
- لا تضع عنوانًا مثل "العرض المقترح"، ولا تضع Markdown أو رموزًا زائدة.
- لا تكرر الوصف حرفيًا؛ حوّله إلى خطة تنفيذ واضحة ومقنعة.

اكتب نص العرض فقط.
"""
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    except Exception as exc:
        raise RuntimeError(f"تعذر توليد عرض Gemini: {exc}") from exc
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini لم يُرجع عرضًا نصيًا")
    return text


def _extract_inline_image(response) -> bytes | None:
    for part in getattr(response, "parts", []) or []:
        inline = getattr(part, "inline_data", None)
        if inline is not None:
            data = getattr(inline, "data", None)
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return base64.b64decode(data)
    return None


def _generate_image_rest(prompt: str, key: str) -> bytes:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "responseMimeType": "image/jpeg"},
    }
    response = requests.post(url, params={"key": key}, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini لم يُرجع بيانات صورة")


def generate_service_image(service: dict[str, Any]) -> bytes:
    """Generate a Khamsat cover and return exactly 1700x970 JPEG."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط في Vercel")
    title = str(service.get("title", "خدمة قانونية")).strip()
    prompt = f"""
أنشئ صورة غلاف لخدمة على خمسات بعنوان: {title}
المجال: خدمات قانونية مصرية، عقود، شركات، استشارات ومراجعة قانونية.
التصميم احترافي وراقي وحديث، عربي، واضح على الهاتف، ويعكس الثقة دون مبالغة.
استخدم عناصر قانونية مجردة مثل عقد وملف وقلم وميزان عدالة، دون أشخاص حقيقيين.
لا تستخدم أي شعار أو علامة تجارية لخمسات أو أي منصة أخرى، ولا أرقام أسعار.
ضع عنوان الخدمة فقط داخل التصميم بخط عربي واضح، واترك هامش أمان واسع حول النص.
لا تضف معلومات أو ادعاءات غير موجودة في العنوان.
النسبة 16:9، وتكوين مناسب لغلاف خدمة احترافي.
"""
    image_bytes: bytes | None = None
    try:
        client = _gemini_client()
        from google.genai import types
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                response_format={"image": {"aspect_ratio": "16:9"}},
            ),
        )
        image_bytes = _extract_inline_image(response)
    except Exception:
        image_bytes = None
    if not image_bytes:
        image_bytes = _generate_image_rest(prompt, key)

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Khamsat requires at least 1700x970; upscale instead of padding a 1024px result.
    target = (1700, 970)
    image.thumbnail(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", target, "white")
    x = (target[0] - image.width) // 2
    y = (target[1] - image.height) // 2
    canvas.paste(image, (x, y))
    if canvas.width < 1700 or canvas.height < 970:
        raise RuntimeError("تعذر تجهيز صورة خمسات بالمقاس المطلوب")
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    return output.getvalue()


def image_data_url(image_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
