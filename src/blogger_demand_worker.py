from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests
from google import genai

from blogger_publisher import build_article_html, prepare_article, service as blogger_rest_service, blog_id as resolve_blog_id
from blogger_ui_publisher import publish_article_ui
from legal_research import research_legal_topic

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip()
BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "").strip()
MAP_PATH = Path(os.getenv("BLOGGER_KEYWORD_MAP_PATH", "data/blogger_keyword_map.json"))
TIMEOUT = 18
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AskMahmoudLegalResearch/1.0)"}

# Seeds are problem-oriented, Egyptian-law topics. Search suggestions expand them
# into natural questions rather than treating these seeds as search-volume data.
SEEDS = [
    "الابتزاز الإلكتروني في مصر",
    "الفصل التعسفي ومستحقات العامل",
    "الإيجار القديم والجديد وحقوق المستأجر",
    "نفقة الزوجة والأطفال وإجراءات التنفيذ",
    "حضانة الأطفال والرؤية في القانون المصري",
    "إيصال الأمانة والشيك بدون رصيد",
    "التعويض عن الضرر في القانون المصري",
    "الاستيلاء المؤقت على العقار للمنفعة العامة",
    "تأسيس الشركات ومسؤولية المدير",
    "تأخر صاحب العمل في صرف المرتب",
    "فسخ العقد والشرط الجزائي",
    "امتناع أحد الورثة عن تقسيم التركة",
    "التصالح في مخالفات البناء",
    "مستحقات نهاية الخدمة في مصر",
    "السب والقذف والتشهير عبر الإنترنت",
    "التوقيع على بياض واسترداد الحق",
    "رفض تسليم الوحدة العقارية",
    "حقوق الشريك عند الخلاف في الشركة",
    "الفصل من العمل بدون إنذار",
    "استرداد الأموال في النصب العقاري",
    "التظلم من قرار إداري في مصر",
    "حقوق العامل في ساعات العمل الإضافية",
    "إجراءات رفع دعوى تعويض",
    "مسؤولية المدير عن ديون الشركة",
    "امتناع الورثة عن بيع أو تقسيم العقار",
    "حقوق الموظف عند انتهاء عقد العمل",
]

AR_STOP = {
    "في", "من", "على", "عن", "الى", "إلى", "ما", "ماذا", "كيف", "هل", "مع",
    "عند", "بعد", "قبل", "مصر", "المصري", "المصرية", "قانون", "القانون",
    "حقوق", "حق", "إجراءات", "طريقة", "شرح", "ماهي", "ماهو", "التي", "الذي",
    "هذا", "هذه", "ذلك", "ولا", "إذا", "لو", "لدى", "بشأن", "بين", "أو",
}
QUESTION_TERMS = ("ازاي", "كيف", "ماذا", "هل", "متى", "عقوبة", "حقوق", "إجراءات", "طريقة", "أعمل", "أفعل", "مستحقات")
LEGAL_TERMS = ("قانون", "حقوق", "محكمة", "دعوى", "عقد", "إيجار", "عمل", "تعويض", "ورثة", "نفقة", "حضانة", "شيك", "أمانة", "ابتزاز", "فصل", "إخلاء", "شركة", "عقار", "ترخيص", "مخالفة", "تظلم", "مستحقات")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: str) -> str:
    value = _clean(value).casefold()
    value = re.sub(r"[ـًٌٍَُِّْٰ]", "", value)
    value = re.sub(r"[إأآٱ]", "ا", value)
    value = value.replace("ى", "ي").replace("ة", "ه")
    tokens = re.findall(r"[\u0600-\u06ff]+|[a-z0-9]+", value)
    return " ".join(x for x in tokens if x not in AR_STOP and len(x) > 1)


def _similarity(a: str, b: str) -> float:
    aa, bb = set(_norm(a).split()), set(_norm(b).split())
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _suggest(query: str) -> list[str]:
    try:
        response = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "q": query, "hl": "ar", "gl": "eg"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return list(dict.fromkeys(_clean(x) for x in (data[1] if isinstance(data, list) and len(data) > 1 else []) if _clean(x)))
    except Exception as exc:
        print(f"Autocomplete unavailable for {query!r}: {exc}")
        return []


def _serp(query: str) -> list[dict[str, str]]:
    """Collect public result titles/snippets as context; not a source of search-volume claims."""
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "eg-ar"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        from html import unescape
        text = response.text
        pattern = re.compile(
            r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            re.I | re.S,
        )
        out = []
        for match in pattern.finditer(text):
            url = unescape(match.group(1))
            title = _clean(re.sub(r"<[^>]+>", " ", unescape(match.group(2))))
            if title and url.startswith("http"):
                out.append({"title": title, "url": url})
            if len(out) >= 6:
                break
        return out
    except Exception as exc:
        print(f"SERP context unavailable for {query!r}: {exc}")
        return []


def _trending_legal_terms() -> list[str]:
    """Use Egypt's public trending feed only as an optional recency signal."""
    url = "https://trends.google.com/trending/rss?geo=EG"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        terms = []
        for item in root.findall(".//item"):
            title = _clean(item.findtext("title", ""))
            if title and any(term in title for term in LEGAL_TERMS):
                terms.append(title)
        return terms[:20]
    except Exception as exc:
        print(f"Google Trends Egypt feed unavailable (optional): {exc}")
        return []


def _public_titles() -> list[dict[str, str]]:
    """Read recent public posts from Blogger's public JSON feed; no OAuth needed."""
    url = BLOG_URL.rstrip("/") + "/feeds/posts/default"
    try:
        response = requests.get(url, params={"alt": "json", "max-results": "100"}, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json().get("feed", {}).get("entry", [])
        out = []
        for item in data:
            title = _clean(item.get("title", {}).get("$t", ""))
            links = item.get("link", [])
            href = next((x.get("href", "") for x in links if x.get("rel") == "alternate"), "")
            if title:
                out.append({"title": title, "url": href})
        return out
    except Exception as exc:
        print(f"Blogger public feed unavailable; keyword-map history remains active: {exc}")
        return []


def _load_map() -> dict:
    try:
        data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("history", [])
            data.setdefault("keyword_frequency", {})
            return data
    except Exception:
        pass
    return {
        "schema_version": 1,
        "description": "Observed Egyptian Arabic legal search queries and daily Blogger research articles. Suggestions/SERP are directional demand signals, not exact search volumes.",
        "history": [],
        "keyword_frequency": {},
    }


def _save_map(data: dict) -> None:
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_candidates(
    history: list[dict],
    published: list[dict[str, str]],
    trends: list[str],
    search_console_rows: list[dict] | None = None,
) -> list[dict]:
    seen = set()
    candidates = []
    recent_queries = [
        str(item.get("query", ""))
        for item in history[-45:]
        if str(item.get("status", "")).upper() == "PUBLISHED"
    ]
    existing_titles = [item.get("title", "") for item in published]
    # Real Search Console impressions/clicks take precedence over proxy signals
    # when a query is already bringing visitors to the site.
    for row in search_console_rows or []:
        query = _clean(row.get("query", ""))
        norm = _norm(query)
        if not norm or len(query) < 8 or norm in seen:
            continue
        if not any(term in query for term in LEGAL_TERMS):
            continue
        if any(_similarity(query, old) >= 0.52 for old in recent_queries if old):
            continue
        if any(_similarity(query, title) >= 0.56 for title in existing_titles if title):
            continue
        seen.add(norm)
        impressions = float(row.get("impressions", 0) or 0)
        clicks = float(row.get("clicks", 0) or 0)
        position = float(row.get("position", 100) or 100)
        ctr = float(row.get("ctr", 0) or 0)
        score = min(100, 45 + min(impressions / 20, 30) + min(clicks, 10) + (15 if 5 <= position <= 20 else 5 if position < 35 else 0) + (10 if impressions >= 50 and ctr < 0.04 else 0))
        candidates.append({
            "query": query,
            "seed": query,
            "suggestions": [],
            "suggestion_count": 0,
            "trend_matches": [],
            "demand_score": round(score, 2),
            "demand_signal": "GOOGLE_SEARCH_CONSOLE_OBSERVED",
            "search_console": {
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "average_position": position,
            },
        })
    for seed in SEEDS:
        # One autocomplete request per seed. Reuse its returned suggestions as
        # demand evidence rather than issuing two more requests for every candidate.
        seed_suggestions = _suggest(seed)
        time.sleep(0.08)
        if not seed_suggestions:
            seed_suggestions = [seed]
        for query in [seed, *seed_suggestions]:
            query = _clean(query)
            norm = _norm(query)
            if not norm or len(query) < 10 or norm in seen:
                continue
            seen.add(norm)
            if not any(term in query for term in LEGAL_TERMS):
                continue
            if any(_similarity(query, old) >= 0.52 for old in recent_queries if old):
                continue
            if any(_similarity(query, title) >= 0.56 for title in existing_titles if title):
                continue
            question_score = sum(1 for term in QUESTION_TERMS if term in query)
            trend_matches = [term for term in trends if _similarity(term, query) >= 0.25]
            score = min(100, 20 + len(seed_suggestions) * 4 + question_score * 5 + len(trend_matches) * 15)
            candidates.append({
                "query": query,
                "seed": seed,
                "suggestions": seed_suggestions[:12],
                "suggestion_count": len(seed_suggestions),
                "trend_matches": trend_matches,
                "demand_score": score,
                "demand_signal": "Google Autocomplete + public SERP context; optional Google Trends Egypt match",
            })
    candidates.sort(key=lambda x: (x["demand_score"], len(x["query"])), reverse=True)
    return candidates


def _generate_source_draft(api_key: str, model: str, query: str, packet: str, serp: list[dict[str, str]]) -> str:
    client = genai.Client(api_key=api_key)
    serp_context = "\n".join(f"- {x['title']} ({x['url']})" for x in serp[:6]) or "No public SERP snippets retrieved."
    prompt = f"""أنت باحث ومحرر قانوني مصري. اكتب مسودة عربية أصلية تجيب مباشرة عن سؤال البحث التالي:
{query}

هذه نتائج بحث عامة للاستدلال على صياغة سؤال المستخدم فقط، وليست مراجع قانونية موثوقة:
{serp_context}

حزمة البحث القانوني المتحقق منها:
{packet}

شروط إلزامية:
- اكتب بالعربية المصرية المهنية الواضحة، وابدأ بإجابة مباشرة.
- استخدم القانون المصري فقط، ولا تخترع أرقام مواد أو عقوبات أو مواعيد أو أحكامًا.
- إذا لم تتضمن حزمة البحث سندًا موثقًا، لا تنسب إليها قاعدة قانونية محددة؛ وضّح الوقائع والمستندات والأسئلة التي يجب التحقق منها.
- اشرح السيناريوهات المحتملة، المستندات التي تغيّر التقييم، الأخطاء الشائعة، والخطوات العملية الآمنة.
- لا تكرر مقالًا عامًا؛ اجعل المقال خاصًا بسؤال البحث.
- أخرج مسودة بين 500 و750 كلمة تصلح أساسًا لمقال متخصص، من دون تسويق أو ادعاء وجود حجم بحث رقمي.
"""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"max_output_tokens": 7000},
    )
    draft = _clean(getattr(response, "text", ""))
    if len(draft) < 900:
        raise RuntimeError("Demand article source draft is too short; refusing to publish thin content.")
    return draft


def _fallback_demand_article(query: str, legal_sources: str) -> dict:
    """Create a cautious, query-specific article when every configured model is quota-limited."""
    source_text = _clean(legal_sources)
    if len(source_text) < 120:
        raise RuntimeError("Legal research packet is too short for a safe fallback article.")
    title = query.rstrip("؟?.!،: ")
    if "عقوبة" in title:
        title = f"{title}: ما الذي يحدد التكييف القانوني؟"
    else:
        title = f"{title}: الأدلة والخطوات القانونية التي يجب مراجعتها"
    title = title[:110].rstrip()
    description = f"دليل عملي حول {query} يوضح الوقائع والأدلة والمستندات والخطوات التي يجب التحقق منها قبل اتخاذ إجراء قانوني في مصر."[:180]
    article = {
        "title": title,
        "meta_description": description,
        "excerpt": f"نقاط عملية لمراجعة موضوع {query} من واقع الوقائع والمستندات والمصادر القانونية المتاحة.",
        "lead": (
            f"إذا كنت تبحث عن «{query}»، فلا يكفي الاعتماد على عنوان المشكلة أو على إجابة عامة متداولة. "
            "يبدأ التقييم القانوني بتحديد ما حدث بدقة، ومتى حدث، وصفة كل طرف، وما إذا كانت هناك مراسلات أو مستندات تثبت الوقائع. "
            "هذا الدليل يركز على خطوات التحقق الآمنة، ولا يفترض نتيجة قانونية واحدة لكل الحالات."
        ),
        "sections": [
            {
                "heading": "حدد الواقعة قبل اختيار الإجراء",
                "body": (
                    f"اكتب تسلسلًا زمنيًا واضحًا لما حدث في موضوع «{query}». ميّز بين ما شاهدته بنفسك، وما ورد في رسالة أو مستند، "
                    "وما سمعته من طرف آخر. وحدد الأشخاص أو الجهات المعنية، والطلبات أو الالتزامات محل الخلاف، وأي إجراء سبق اتخاذه. "
                    "هذه التفاصيل تساعد على تحديد المسألة القانونية الصحيحة بدلًا من تطبيق قاعدة عامة على واقعة مختلفة."
                ),
            },
            {
                "heading": "اجمع الأدلة والمستندات واحفظ أصلها",
                "body": (
                    "احتفظ بالعقود والإيصالات والإخطارات والمراسلات وسجلات التواصل والملفات الأصلية ذات الصلة، مع تواريخها وبياناتها "
                    "قدر الإمكان. لا تعدّل الملفات ولا تحذف المحادثات، ولا تنشر بيانات شخصية أو محتوى خاصًا على الملأ. "
                    "رتب الأدلة حسب التاريخ، واكتب ما الذي يثبته كل مستند وما النقطة التي لا يزال إثباتها ناقصًا."
                ),
            },
            {
                "heading": "ما الذي يجب التحقق منه قانونيًا؟",
                "body": (
                    "لا تستنتج العقوبة أو الحق أو ميعاد الإجراء من عنوان البحث وحده. يجب التحقق من النص القانوني الساري، "
                    "وانطباقه على الوقائع المحددة، وصفة الأطراف، والاختصاص، وأي شروط أو مواعيد أو إجراءات لازمة. "
                    "تتضمن حزمة البحث القانونية المتاحة لهذا الموضوع مواد مرجعية للمراجعة؛ ويجب التأكد من النصوص الأصلية وحداثتها "
                    "قبل الاعتماد على رقم مادة أو عقوبة أو ميعاد محدد."
                ),
            },
            {
                "heading": "خطوات عملية قبل تقديم بلاغ أو اتخاذ إجراء",
                "body": (
                    "جهّز ملخصًا موجزًا للوقائع، وقائمة بالمستندات، وبيانات الأطراف، والتواريخ المهمة، والنتيجة التي تريد الوصول إليها. "
                    "تحقق من الجهة المختصة وطريقة تقديم الطلب أو الشكوى ومتطلبات إثبات الاستلام. إذا كان هناك خطر مستمر أو موعد قريب، "
                    "اطلب مساعدة قانونية مناسبة بسرعة بدلًا من انتظار إجابة عامة على الإنترنت."
                ),
            },
            {
                "heading": "أخطاء شائعة ينبغي تجنبها",
                "body": (
                    "تجنب حذف الأدلة، أو تعديل المستندات، أو توجيه اتهامات علنية غير موثقة، أو توقيع إقرار أو تسوية قبل فهم آثارها. "
                    "ولا تفترض أن حالتين متشابهتين في العنوان لهما النتيجة نفسها؛ فقد تغيّر التفاصيل والمستندات والإجراءات التقييم. "
                    "قبل أي خطوة يصعب الرجوع عنها، راجع الوقائع والمصدر القانوني والإجراء المناسب."
                ),
            },
        ],
        "faq": [
            {
                "question": "هل يحدد عنوان البحث النتيجة القانونية وحده؟",
                "answer": "لا؛ التقييم يعتمد على الوقائع المثبتة والمستندات وصفة الأطراف والنصوص والإجراءات المنطبقة.",
            },
            {
                "question": "ما أهم شيء أبدأ به؟",
                "answer": "ترتيب الوقائع زمنيًا وحفظ المستندات والمراسلات الأصلية وتحديد الإجراء المطلوب.",
            },
            {
                "question": "هل يمكن الجزم بعقوبة أو ميعاد من دون مراجعة المصادر؟",
                "answer": "لا ينبغي الجزم برقم مادة أو عقوبة أو ميعاد قبل التحقق من النص القانوني الساري وانطباقه على الواقعة.",
            },
        ],
        "keywords": list(dict.fromkeys([query, "القانون المصري", "إجراءات قانونية", "المستندات والأدلة"])),
    }
    return article


def _related_public_posts(published: list[dict[str, str]], topic: str) -> list[dict[str, str]]:
    related = []
    seen = set()
    for item in sorted(published, key=lambda x: _similarity(topic, x.get("title", "")), reverse=True):
        title = _clean(item.get("title", ""))
        url = _clean(item.get("url", ""))
        score = _similarity(topic, title)
        if not title or not url or url in seen or score < 0.12:
            continue
        if score >= 0.9:
            continue
        seen.add(url)
        related.append({"title": title, "url": url})
        if len(related) >= 3:
            break
    return related


def _find_public_url(title: str, fallback: str) -> str:
    for attempt in range(5):
        for item in _public_titles():
            if _norm(item["title"]) == _norm(title) and item.get("url"):
                return item["url"]
        if attempt < 4:
            time.sleep(2)
    return fallback


def main() -> int:
    if os.getenv("BLOGGER_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        print("Blogger is disabled; daily search-demand article skipped.")
        return 0
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for the daily Blogger search-demand article.")
    if not os.getenv("BLOGGER_UI_STORAGE_STATE_B64", "").strip():
        raise RuntimeError("BLOGGER_UI_STORAGE_STATE_B64 is required; this worker publishes through the existing authenticated Blogger UI.")

    cairo_now = datetime.now(ZoneInfo("Africa/Cairo"))
    # This worker is scheduled independently from social publishing and runs once
    # per Cairo calendar day; idempotency below prevents duplicate articles.
    today = cairo_now.date().isoformat()
    keyword_map = _load_map()
    history = keyword_map["history"]
    published = _public_titles()
    existing_today = next(
        (item for item in reversed(history)
         if item.get("date") == today and item.get("status") in {"PUBLISHED", "PUBLISH_UNVERIFIED"}),
        None,
    )
    if existing_today:
        stored_title = str(existing_today.get("title", "") or "").strip()
        verified_url = next(
            (item.get("url", "") for item in published
             if _norm(item.get("title", "")) == _norm(stored_title) and item.get("url")),
            "",
        )
        # A Blogger dashboard URL (?postId=...) is not a public permalink.
        # Old runs incorrectly marked that private URL as PUBLISHED, which made
        # every later daily run skip forever even though the public feed had no post.
        if verified_url and "postId=" not in verified_url:
            if existing_today.get("post_url") != verified_url or existing_today.get("status") != "PUBLISHED":
                existing_today["post_url"] = verified_url
                existing_today["status"] = "PUBLISHED"
                _save_map(keyword_map)
                print(f"Existing demand article public permalink verified: {verified_url}")
            print(f"Daily Blogger search-demand article already publicly published for {today}; idempotent skip.")
            return 0
        existing_today["status"] = "PUBLISH_UNVERIFIED"
        existing_today["post_url"] = ""
        existing_today.pop("post_id", None)
        _save_map(keyword_map)
        print(
            "Previous demand run was a false positive: no public permalink exists for today's article. "
            "Retrying publication instead of idempotently skipping."
        )
    trends = _trending_legal_terms()
    search_console_rows = []
    if os.getenv("SEARCH_CONSOLE_SITE_URL", "").strip() and (
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        or os.getenv("GOOGLE_CREDENTIALS", "").strip()
    ):
        try:
            from search_console_intelligence import query_search_console
            search_console_rows = query_search_console(
                days=max(1, int(os.getenv("SEARCH_CONSOLE_DAYS", "28")))
            )
            print(f"Google Search Console queries retrieved: {len(search_console_rows)}")
        except Exception as exc:
            print(f"Search Console data unavailable; using autocomplete/SERP demand signals: {exc}")
    candidates = collect_candidates(history, published, trends, search_console_rows)
    if not candidates:
        raise RuntimeError("No distinct legal search-demand candidate found after deduplication.")
    selected = candidates[0]
    query = selected["query"]
    print(f"Selected search-demand query: {query}")
    print(f"Directional demand score: {selected['demand_score']} (not a search-volume estimate)")
    print(f"Autocomplete suggestions: {selected['suggestions']}")
    serp = _serp(f'"{query}" مصر قانون')
    packet = research_legal_topic(query)
    model = os.getenv("GEMINI_MODEL", "").strip() or os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or "gemini-3.6-flash"
    # Keep this to one successful Gemini generation call. Repeated daily
    # workers previously exhausted the free-tier request quota with draft+rewrite.
    serp_brief = "\n".join(f"- {x['title']}: {x['url']}" for x in serp[:5])
    search_brief = (
        "موجز مقال مستقل مبني على نية البحث، وليس منشورًا اجتماعيًا. "
        f"سؤال البحث الأساسي: {query}\n"
        "استخدم نتائج البحث التالية لفهم الأسئلة الفرعية فقط، ولا تعتبرها سندًا قانونيًا:\n"
        f"{serp_brief or 'لا توجد نتائج بحث عامة متاحة.'}\n"
        "اكتب مقالًا متخصصًا جديدًا يجيب عن السؤال، ويشرح الوقائع والمستندات والخطوات العملية، "
        "ولا تخترع قاعدة أو رقم مادة أو عقوبة أو موعدًا."
    )
    article = None
    generation_errors = []
    model_candidates = list(dict.fromkeys(
        candidate for candidate in [
            model,
            os.getenv("GEMINI_FALLBACK_MODEL", "").strip(),
            "gemini-3.8-flash",
        ]
        if candidate and candidate.casefold().removeprefix("models/") != "gemini-2.5-flash"
    ))
    for candidate_model in (x for x in model_candidates if x):
        try:
            article = prepare_article(
                api_key=api_key,
                model=candidate_model,
                topic=query,
                post=search_brief,
                legal_sources=packet,
            )
            print(f"Demand article generated with model {candidate_model}.")
            break
        except Exception as exc:
            generation_errors.append(f"{candidate_model}: {exc}")
            print(f"Demand article generation failed with {candidate_model}: {exc}")
    if not isinstance(article, dict):
        print("All configured Gemini models are unavailable; building a cautious article from the verified research packet. " + " | ".join(generation_errors))
        article = _fallback_demand_article(query, packet)
    title = _clean(article.get("title", ""))[:110]
    description = _clean(article.get("meta_description", ""))[:180]
    if not title or len(description) < 40:
        raise RuntimeError("SEO article title or search description is missing; refusing to publish incomplete metadata.")
    keywords = [ _clean(x) for x in article.get("keywords", []) if _clean(x) ]
    labels = list(dict.fromkeys(["قانون مصر", "اسأل محمود", *keywords]))[:10]
    html = build_article_html(
        title=title,
        topic=query,
        post=str(article.get("lead", "") or search_brief),
        image_url="",
        legal_sources=packet,
        related=_related_public_posts(published, query),
        article=article,
    )
    history_entry = {
        **selected,
        "date": today,
        "status": "PROCESSING",
        "title": title,
        "keywords": keywords,
        "meta_description": description,
        "serp_titles": [x["title"] for x in serp],
        "serp_urls": [x["url"] for x in serp],
        "research_date": today,
    }
    history.append(history_entry)
    _save_map(keyword_map)

    if os.getenv("BLOGGER_OAUTH_JSON", "").strip():
        try:
            blogger_api = blogger_rest_service()
            target_blog_id = BLOG_ID or resolve_blog_id(blogger_api, BLOG_URL)
            response = blogger_api.posts().insert(
                blogId=target_blog_id,
                body={
                    "kind": "blogger#post",
                    "title": title,
                    "content": html,
                    "labels": labels,
                },
                isDraft=False,
            ).execute()
            result = {
                "post_id": str(response.get("id", "")),
                "post_url": str(response.get("url", "")),
                "title": str(response.get("title", title)),
                "publisher": "BLOGGER_REST_API",
            }
            if not result["post_id"] or not result["post_url"]:
                raise RuntimeError("Blogger REST API did not return a verifiable published post ID and URL.")
            print("Demand article published through Blogger REST API.")
        except Exception as api_exc:
            print(f"Blogger REST API unavailable; trying the saved authenticated UI session: {api_exc}")
            result = publish_article_ui(
                title=title,
                content_html=html,
                labels=labels,
                blog_id=BLOG_ID,
                blog_url=BLOG_URL,
                search_description=description,
            )
    else:
        print("BLOGGER_OAUTH_JSON is absent; using the authenticated Blogger UI publisher.")
        result = publish_article_ui(
            title=title,
            content_html=html,
            labels=labels,
            blog_id=BLOG_ID,
            blog_url=BLOG_URL,
            search_description=description,
        )
    public_url = _find_public_url(title, result.get("post_url", ""))
    if not public_url or "postId=" in public_url:
        history_entry.update({
            "status": "PUBLISH_UNVERIFIED",
            "post_id": result.get("post_id", ""),
            "post_url": "",
            "publish_attempted_at": datetime.now(ZoneInfo("Africa/Cairo")).isoformat(),
        })
        _save_map(keyword_map)
        raise RuntimeError(
            "Blogger UI returned no public permalink. The article is NOT marked PUBLISHED; "
            "the next run will retry instead of silently skipping."
        )
    history_entry.update({
        "status": "PUBLISHED",
        "post_id": result.get("post_id", ""),
        "post_url": public_url,
        "published_at": datetime.now(ZoneInfo("Africa/Cairo")).isoformat(),
    })
    frequency = Counter(keyword_map.get("keyword_frequency", {}))
    for keyword in [query, *keywords, *selected["suggestions"]]:
        clean_keyword = _clean(keyword)
        if clean_keyword:
            frequency[clean_keyword] += 1
    keyword_map["keyword_frequency"] = dict(frequency.most_common(500))
    keyword_map["updated_at"] = datetime.now(ZoneInfo("Africa/Cairo")).isoformat()
    _save_map(keyword_map)
    print(f"Daily search-demand article published: {title} -> {public_url}")
    print(f"Keyword map updated: {MAP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
