from __future__ import annotations

import re
import unicodedata


STOPWORDS = {
    "في", "من", "على", "عن", "الى", "إلى", "ما", "هل", "كيف", "متى", "مع",
    "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "و", "او", "أو", "ثم",
    "الذى", "التى", "بين", "بعد", "قبل", "عند", "كل", "وقد",
    "قانون", "القانون", "مصر", "المصري", "المصرية", "دليل", "شرح", "كيفية",
}

FOREIGN_JURISDICTIONS = {
    "الجزائر": ("الجزائر", "الجزائري", "الجزائرية"),
    "السعودية": ("السعودية", "السعودي"),
    "اليمن": ("اليمن", "اليمني", "اليمنية"),
    "الإمارات": ("الإمارات", "الإماراتي", "الإماراتية"),
    "الكويت": ("الكويت", "الكويتي"),
    "قطر": ("قطر", "القطري"),
    "الأردن": ("الأردن", "الأردني", "الأردنية"),
    "لبنان": ("لبنان", "اللبناني", "اللبنانية"),
    "المغرب": ("المغرب", "المغربي", "المغربية"),
    "تونس": ("تونس", "التونسي", "التونسية"),
}


def norm(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"[إأآٱ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", value).strip()


def terms(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9\u0600-\u06ff]+", norm(text))
        if len(word) > 2 and word not in STOPWORDS
    }


def jurisdiction(title: str) -> str:
    normalized = norm(title)
    for country, terms_list in FOREIGN_JURISDICTIONS.items():
        if any(norm(term) in normalized for term in terms_list):
            return country
    return "مصر"


def choose_related(source: dict, posts: list[dict], max_links: int = 2) -> list[dict]:
    source_title = str(source.get("title", ""))
    source_jurisdiction = jurisdiction(source_title)
    source_terms = terms(source_title)
    existing_html = str(source.get("content", "") or "")
    existing_urls = set(re.findall(r'''href\s*=\s*["']([^"']+)["']''', existing_html, flags=re.I))
    candidates = []
    for target in posts:
        if str(target.get("id")) == str(source.get("id")):
            continue
        url = str(target.get("url", "")).strip()
        title = str(target.get("title", "")).strip()
        if not url or not title or url in existing_urls:
            continue
        if jurisdiction(title) != source_jurisdiction:
            continue
        overlap = source_terms & terms(title)
        if len(overlap) < 2:
            continue
        candidates.append((len(overlap), title, url, sorted(overlap)))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"title": title, "url": url, "shared_terms": shared}
        for _, title, url, shared in candidates[:max_links]
    ]
