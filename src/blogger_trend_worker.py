from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests

from blogger_publisher import publish_article
from config import load_blogger_config
from sheets import create_service, get_values
from googleapiclient.errors import HttpError

TZ = ZoneInfo("Africa/Cairo")
BLOG = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip()
LOG_SHEET = "BloggerTrends"
LOG_HEADERS = ["Date Cairo", "Status", "Trend", "Source Title", "Source URL", "Blogger Title", "Blogger URL", "Blogger Post ID", "Error", "Created At"]
LEGAL_TERMS = ("قانون", "قانوني", "تشريع", "تشريعات", "محكمة", "قضية", "قضاء", "وزارة العمل", "العمل", "عمال", "موظف", "تأمينات", "ضرائب", "شركات", "استثمار", "إيجار", "عقارات", "مرور", "أحوال شخصية", "نقابة", "قرار وزاري", "مجلس النواب", "النيابة", "التحقيق")


def _now():
    return datetime.now(TZ)


def _ensure_log_sheet(svc, spreadsheet_id):
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    names = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if LOG_SHEET not in names:
        svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests":[{"addSheet":{"properties":{"title":LOG_SHEET}}}]}).execute()
    svc.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=f"{LOG_SHEET}!A1:J1", valueInputOption="RAW", body={"values":[LOG_HEADERS]}).execute()


def _log(svc, spreadsheet_id, values):
    svc.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=f"{LOG_SHEET}!A:J", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values":[[str(values.get(h, "")) for h in LOG_HEADERS]]}).execute()


def _rss_items(url):
    """Read both RSS 2.0 <item> and Atom <entry> feeds (Google Trends uses Atom)."""
    response = requests.get(url, timeout=25, headers={"User-Agent":"Mozilla/5.0 (compatible; KhyratLegalTrendBot/1.0)"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        desc = " ".join(desc.split())
        if title and link:
            items.append({"title": title, "url": link, "description": desc[:1200]})

    # Atom (Google Trends RSS endpoint)
    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", atom_ns):
        title = (entry.findtext("atom:title", default="", namespaces=atom_ns) or "").strip()
        link = ""
        for link_node in entry.findall("atom:link", atom_ns):
            href = (link_node.attrib.get("href") or "").strip()
            rel = (link_node.attrib.get("rel") or "alternate").strip()
            if href and rel in {"alternate", ""}:
                link = href
                break
        summary = entry.findtext("atom:summary", default="", namespaces=atom_ns) or ""
        desc = " ".join(re.sub(r"<[^>]+>", " ", summary).split())
        if title and link and not any(x["url"] == link for x in items):
            items.append({"title": title, "url": link, "description": desc[:1200]})
    return items

def collect_candidates():
    urls = [
        "https://trends.google.com/trending/rss?geo=EG",
        "https://news.google.com/rss/search?q=" + quote_plus('(قانون OR تشريع OR وزارة العمل OR التأمينات OR الضرائب OR الشركات OR قرار وزاري) when:2d') + "&hl=ar&gl=EG&ceid=EG:ar",
    ]
    found, seen = [], set()
    for url in urls:
        try:
            for item in _rss_items(url):
                key = re.sub(r"[^\w\u0600-\u06ff]", "", item["title"].casefold())
                if key and key not in seen:
                    seen.add(key)
                    found.append(item)
        except Exception as exc:
            print(f"Trend source unavailable: {exc}")
    legal = [x for x in found if any(term in (x["title"] + " " + x["description"]) for term in LEGAL_TERMS)]
    # Prioritize explicit legal/news coverage over broad search-volume trends.
    legal.sort(key=lambda x: (sum(term in (x["title"] + " " + x["description"]) for term in LEGAL_TERMS), len(x["description"])), reverse=True)
    return legal[:12]


def _generate_article_input(candidate):
    return (
        f"الموضوع الرائج المرشح: {candidate['title']}\n"
        f"ملخص المصدر: {candidate['description']}\n"
        f"رابط المصدر الصحفي: {candidate['url']}\n\n"
        "اكتب مقالًا قانونيًا مصريًا أصليًا يشرح أثر الخبر على المواطن أو صاحب العمل أو الشركة بحسب الموضوع. "
        "لا تعتبر الخبر وحده سندًا قانونيًا، ولا تخترع قانونًا أو رقم مادة أو تاريخ نفاذ أو حكم محكمة. "
        "فرّق بوضوح بين ما أورده المصدر وما هو تحليل عام، واذكر أن القارئ يرجع للنص الرسمي المنشور بالجريدة الرسمية أو الجهة المختصة قبل التصرف. "
        "إذا لم يكن الخبر ذا صلة قانونية مصرية مباشرة أو لا توجد معلومات كافية، ارفض الموضوع ولا تنشره. "
        "استخدم لغة مصرية مهنية واضحة، أمثلة عملية، خطوات تحقق، وأخطاء يجب تجنبها. أدرج رابط المصدر داخل المقال. "
        "لا تقدم استشارة قاطعة لحالة فردية ولا تعد بنتيجة قانونية."
    )


def main():
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger disabled; trend article worker exits.")
        return 0
    if not config.get("blogger_oauth_json"):
        raise RuntimeError("BLOGGER_OAUTH_JSON is required for daily trend publishing.")
    today = _now().date().isoformat()
    svc = create_service(config["service_account_info"])
    _ensure_log_sheet(svc, config["sheet_id"])
    history = get_values(svc, config["sheet_id"], f"{LOG_SHEET}!A:J")
    for row in history[1:]:
        if len(row) > 1 and row[0] == today and row[1] == "PUBLISHED":
            print(f"Trend article already published today: {row[6] if len(row)>6 else ''}")
            return 0

    candidates = collect_candidates()
    if not candidates:
        _log(svc, config["sheet_id"], {"Date Cairo":today, "Status":"NO_LEGAL_TREND", "Error":"No sufficiently relevant Egypt legal trend found in Google Trends/Google News RSS.", "Created At":_now().isoformat()})
        print("No verified legal trend candidate today; no generic article will be published.")
        return 0

    # Avoid republishing a topic covered in the last 30 days.
    prior_topics = {str(row[2]).strip().casefold() for row in history[1:] if len(row)>2 and row[1]=="PUBLISHED"}
    candidate = next((x for x in candidates if x["title"].casefold() not in prior_topics), None)
    if candidate is None:
        _log(svc, config["sheet_id"], {"Date Cairo":today, "Status":"DUPLICATE_SKIPPED", "Error":"All relevant trend candidates match previously published titles.", "Created At":_now().isoformat()})
        print("All eligible topics were already covered; skipping duplicate publication.")
        return 0

    topic = candidate["title"]
    post = _generate_article_input(candidate)
    image_path = ""
    try:
        from image_generator import create_legal_image
        target = Path("generated/blogger-trends") / (hashlib.sha1((today+topic).encode("utf-8")).hexdigest()[:12] + ".jpg")
        target.parent.mkdir(parents=True, exist_ok=True)
        create_legal_image(topic=topic, image_brief=post[:1200], visual_description=post[:1200], post_context=post, output_path=str(target), api_key=os.getenv("GEMINI_API_KEY","").strip(), cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID","").strip(), cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN","").strip())
        if target.is_file() and target.stat().st_size:
            image_path = str(target)
    except Exception as exc:
        print(f"Trend article image generation unavailable: {exc}")

    try:
        result = publish_article(topic=topic, post=post, image_path=image_path, legal_sources=f"المصدر الصحفي للخبر (للاطلاع على الواقعة وليس كسند تشريعي): {candidate['url']}", labels=["ترند مصر", "مستجدات قانونية", "قانون مصر", "اسأل محمود"], output_dir="generated/blogger-trends")
        _log(svc, config["sheet_id"], {"Date Cairo":today, "Status":"PUBLISHED", "Trend":topic, "Source Title":candidate["title"], "Source URL":candidate["url"], "Blogger Title":result.get("title",""), "Blogger URL":result.get("post_url",""), "Blogger Post ID":result.get("post_id",""), "Created At":_now().isoformat()})
        print(f"DAILY TREND ARTICLE PUBLISHED: {result.get('post_url','')}")
        return 0
    except Exception as exc:
        _log(svc, config["sheet_id"], {"Date Cairo":today, "Status":"FAILED", "Trend":topic, "Source Title":candidate["title"], "Source URL":candidate["url"], "Error":str(exc)[:1000], "Created At":_now().isoformat()})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
