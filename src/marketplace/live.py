"""Live Marketplace acquisition and AI helpers.

This module only reads publicly visible Mostaql project pages. It never logs in,
submits offers, or automates a user account. Gemini is used to turn each
qualified opportunity into a case-specific proposal and to generate a service
cover image when requested.
"""
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
        "User-Agent": "Mozilla/5.0 (compatible; KhyratMarketplace/2.0; +https://github.com/mr-romel/khyrat-legal-content-engine)",
        "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.7",
    })
    return s


def score_legal_relevance(title: str, description: str) -> tuple[int, list[str]]:
    text = f"{title} {description}".lower()
    hits = [(term, points) for term, points in LEGAL_TERMS.items() if term in text]
    score = min(100, sum(points for _, points in hits))
    reasons = [f"مطابقة قانونية: {term}" for term, _ in hits[:8]]
    if not reasons:
        reasons = ["لا توجد مطابقة قانونية كافية"]
    return score, reasons


def _fetch_project_list(session: requests.Session, url: str, timeout: int = 12) -> list[tuple[str, str]]:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []
    parser = _ProjectParser()
    parser.feed(response.text)
    return parser.links


def _detail(session: requests.Session, url: str) -> dict[str, str]:
    try:
        response = session.get(url, timeout=8)
        response.raise_for_status()
        parser = _ProjectParser()
        parser.feed(response.text)
        description = parser.meta.get("description") or parser.meta.get("og:description") or ""
        return {"description": description[:6000]}
    except requests.RequestException:
        # Jina Reader is used only as a public-page fallback when Mostaql's
        # normal HTML response is blocked by an intermediary or edge cache.
        reader_url = "https://r.jina.ai/http://" + url.removeprefix("https://")
        try:
            response = session.get(reader_url, timeout=8)
            response.raise_for_status()
            return {"description": response.text[:6000]}
        except requests.RequestException:
            return {"description": ""}


def fetch_mostaql_projects(limit: int = 12, minimum_score: int = 30) -> list[dict[str, Any]]:
    """Fetch current public legal projects and retain relevant opportunities."""
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

    # Last fallback: the generic projects page. It is intentionally secondary
    # because the legal skill feed is a much better acquisition source.
    if not unique:
        for href, title in _fetch_project_list(session, MOSTAQL_PROJECTS_URL):
            url = urljoin(MOSTAQL_PROJECTS_URL, href)
            if re.search(r"/project/\d+", url):
                unique.setdefault(url, title)
            if len(unique) >= limit * 5:
                break

    candidates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_detail, session, url): (url, title)
            for url, title in list(unique.items())[:limit * 4]
        }
        for future in as_completed(futures):
            url, title = futures[future]
            detail = future.result()
            description = detail.get("description", "")
            score, reasons = score_legal_relevance(title, description)
            if score < minimum_score:
                continue
            candidates.append({
                "platform": "mostaql",
                "title": title,
                "description": description or title,
                "source_url": url,
                "match_score": score,
                "rationale": reasons,
                "acquisition_score": score,
            })

    candidates.sort(key=lambda item: item["match_score"], reverse=True)
    return candidates[:limit]


def _gemini_client():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط في Vercel")
    from google import genai
    return genai.Client(api_key=key)


def generate_case_specific_offer(opportunity: dict[str, Any]) -> str:
    """Ask Gemini for a tailored Arabic proposal for one concrete project."""
    client = _gemini_client()
    title = str(opportunity.get("title", "")).strip()
    description = str(opportunity.get("description", "")).strip()
    prompt = f"""
أنت مستشار لتقديم عروض احترافية على منصة مستقل لمستشار قانوني مصري متخصص في
قانون الشركات والعقود والعمل والقانون التجاري. اكتب عرضًا عربيًا مصريًا مهنيًا
ومقنعًا لهذا المشروع تحديدًا، وليس قالبًا عامًا.

المشروع:
العنوان: {title}
الوصف: {description}

قواعد مهمة:
- حلل المطلوب أولًا، ثم ابنِ العرض على احتياج صاحب المشروع نفسه.
- لا تدّعِ خبرة أو عملاً سابقًا لم يذكره المستخدم.
- لا تستخدم افتتاحيات محفوظة أو كلامًا تسويقيًا عامًا.
- اذكر نقطة أو نقطتين من المشروع تثبت أنك فهمته.
- وضّح منهج التنفيذ والمخرجات المتوقعة.
- إذا كان هناك نقص في المعلومات، اسأل سؤالًا واحدًا ذكيًا فقط في نهاية العرض.
- اجعل العرض بين 130 و220 كلمة تقريبًا.
- لا تضع روابط خارجية، ولا تطلب التواصل خارج مستقل.
- لا تذكر أنك ذكاء اصطناعي.
- اكتب العرض فقط دون عناوين مثل "العرض المقترح".
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini لم يُرجع عرضًا نصيًا")
    return text


def generate_service_image(service: dict[str, Any]) -> bytes:
    """Generate a Khamsat-ready cover image and normalize it to 1700x970 JPEG."""
    client = _gemini_client()
    title = str(service.get("title", "خدمة قانونية")).strip()
    prompt = f"""
صمم غلاف خدمة احترافي لخمسات لخدمة قانونية مصرية بعنوان: {title}.
المجال: محاماة، عقود، شركات، قانون مصري.
التصميم عربي حديث وراقي، يوحي بالثقة والاحتراف، بدون صور أشخاص حقيقيين،
بدون شعارات أو علامات تجارية تخص مواقع أخرى، وبدون أرقام أسعار أو بيانات مضللة.
ضع عنوان الخدمة فقط بخط عربي واضح وكبير، مع عناصر بصرية قانونية بسيطة مثل
ملف عقد، قلم، ميزان عدالة أو أوراق رسمية. اترك مساحات آمنة حول النص.
نسبة العرض 16:9 تقريبًا.
"""
    from google.genai import types
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for part in response.parts:
        if getattr(part, "inline_data", None) is not None:
            image = part.as_image()
            image.thumbnail((1700, 970), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (1700, 970), "white")
            x = (1700 - image.width) // 2
            y = (970 - image.height) // 2
            canvas.paste(image.convert("RGB"), (x, y))
            output = io.BytesIO()
            canvas.save(output, format="JPEG", quality=72, optimize=True)
            return output.getvalue()
    raise RuntimeError("Gemini لم يُرجع صورة")


def image_data_url(image_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
