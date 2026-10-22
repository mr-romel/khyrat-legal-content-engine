from __future__ import annotations

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests

BLOG_URL = "https://askmahmoudkhyrat.blogspot.com/"
TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KhyratLegalSEOAudit/1.0)"}


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def norm_title(value: str) -> str:
    value = clean(value).casefold()
    value = re.sub(r"[ـًٌٍَُِّْٰ]", "", value)
    value = re.sub(r"[إأآٱ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    return " ".join(re.findall(r"[\w\u0600-\u06ff]+", value))


def fetch(url: str) -> tuple[int, str, str]:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    return response.status_code, response.url, response.text


def run(output_dir: str = "artifacts/seo-audit") -> dict:
    session = requests.Session()
    session.headers.update(HEADERS)
    findings: list[dict] = []
    checks: list[dict] = []

    def check(name: str, url: str, required: bool = True) -> tuple[int | None, str, str]:
        try:
            response = None
            for attempt in range(3):
                try:
                    response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if response.status_code not in {408, 425, 429, 500, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(1.5 * (attempt + 1))
            ok = 200 <= response.status_code < 300
            checks.append({"name": name, "url": url, "final_url": response.url,
                           "status": response.status_code, "ok": ok, "required": required})
            if not ok and required:
                findings.append({"severity": "HIGH", "code": "ENDPOINT_HTTP_ERROR",
                                 "message": f"{name} returned HTTP {response.status_code}", "url": url})
            return response.status_code, response.url, response.text
        except requests.RequestException as exc:
            checks.append({"name": name, "url": url, "final_url": "", "status": None,
                           "ok": False, "required": required, "error": str(exc)})
            if required:
                findings.append({"severity": "HIGH", "code": "ENDPOINT_UNREACHABLE",
                                 "message": f"{name} could not be fetched: {exc}", "url": url})
            return None, "", ""

    base = BLOG_URL.rstrip("/")
    _, _, home = check("homepage", base + "/")
    _, _, feed = check("public_posts_feed", base + "/feeds/posts/default?alt=json&max-results=500")
    _, _, sitemap = check("sitemap", base + "/sitemap.xml")
    _, _, robots = check("robots_txt", base + "/robots.txt", required=False)

    entries: list[dict] = []
    try:
        data = json.loads(feed) if feed else {}
        raw_entries = data.get("feed", {}).get("entry", [])
        for entry in raw_entries:
            title = clean((entry.get("title") or {}).get("$t", ""))
            content_html = str((entry.get("content") or {}).get("$t", "") or "")
            content = clean(re.sub(r"<[^>]+>", " ", content_html))
            links = entry.get("link", [])
            url = next((x.get("href", "") for x in links if x.get("rel") == "alternate"), "")
            published = clean((entry.get("published") or {}).get("$t", ""))
            updated = clean((entry.get("updated") or {}).get("$t", ""))
            if title:
                entries.append({"title": title, "normalized_title": norm_title(title),
                                "url": url, "content_chars": len(content), "content_html": content_html,
                                "published": published, "updated": updated})
        checks.append({"name": "feed_parse", "ok": bool(entries), "entry_count": len(entries)})
        if not entries:
            findings.append({"severity": "HIGH", "code": "EMPTY_OR_INVALID_FEED",
                             "message": "The public Blogger feed parsed but returned no titled posts."})
    except (ValueError, TypeError, AttributeError) as exc:
        findings.append({"severity": "HIGH", "code": "FEED_PARSE_ERROR",
                         "message": f"Could not parse Blogger JSON feed: {exc}"})

    counts = Counter(x["normalized_title"] for x in entries if x["normalized_title"])
    for item in entries:
        if counts[item["normalized_title"]] > 1:
            findings.append({"severity": "MEDIUM", "code": "DUPLICATE_TITLE",
                             "message": f"Exact normalized title appears {counts[item['normalized_title']]} times.",
                             "title": item["title"], "url": item["url"]})
        if item["content_chars"] < 500:
            findings.append({"severity": "MEDIUM", "code": "THIN_OR_EMPTY_POST",
                             "message": f"Post content has only {item['content_chars']} extracted characters; review manually.",
                             "title": item["title"], "url": item["url"]})
        if not item["url"]:
            findings.append({"severity": "HIGH", "code": "MISSING_PUBLIC_PERMALINK",
                             "message": "Feed entry has no alternate permalink.", "title": item["title"]})
        elif urlparse(item["url"]).netloc != urlparse(base).netloc:
            findings.append({"severity": "LOW", "code": "EXTERNAL_ALTERNATE_URL",
                             "message": "Alternate permalink points outside the configured blog host.",
                             "title": item["title"], "url": item["url"]})

    # Audit contextual links between posts present in the public Blogger feed.
    known_urls = {str(item.get("url", "")).split("#", 1)[0].rstrip("/") for item in entries if item.get("url")}
    internal_link_count = 0
    posts_without_internal_links = []
    for item in entries:
        hrefs = re.findall("href=[\\\"']([^\\\"']+)[\\\"']", item.get("content_html", ""), flags=re.I)
        links = []
        for href in hrefs:
            absolute = urljoin(item.get("url", ""), unescape(href)).split("#", 1)[0].rstrip("/")
            parsed = urlparse(absolute)
            if parsed.scheme in {"http", "https"} and parsed.netloc.casefold() == urlparse(base).netloc.casefold() and absolute in known_urls and absolute != str(item.get("url", "")).rstrip("/") and absolute not in links:
                links.append(absolute)
        item["internal_links_to_known_posts"] = links
        internal_link_count += len(links)
        if not links and item.get("url"):
            posts_without_internal_links.append({"title": item["title"], "url": item["url"]})
            findings.append({"severity": "MEDIUM", "code": "NO_INTERNAL_POST_LINKS", "message": "No contextual link to another post in the public feed was detected.", "title": item["title"], "url": item["url"]})

    sitemap_urls = []
    is_sitemap_index = False
    try:
        root = ET.fromstring(sitemap) if sitemap else None
        if root is not None:
            sitemap_urls = [node.text.strip().split("#", 1)[0].rstrip("/")
                            for node in root.iter()
                            if node.tag.endswith("loc") and node.text and node.text.strip()]
            checks.append({"name": "sitemap_parse", "ok": bool(sitemap_urls),
                           "url_count": len(sitemap_urls)})
            if not sitemap_urls:
                findings.append({"severity": "MEDIUM", "code": "SITEMAP_NO_URLS",
                                 "message": "Sitemap returned successfully but no loc URLs were parsed."})
            if root.tag.endswith("sitemapindex"):
                is_sitemap_index = True
                findings.append({"severity": "LOW", "code": "SITEMAP_INDEX",
                                 "message": "Sitemap endpoint is an index; nested sitemap URLs are listed but not fetched individually."})
    except ET.ParseError as exc:
        findings.append({"severity": "HIGH", "code": "SITEMAP_PARSE_ERROR",
                         "message": f"Sitemap is not valid XML: {exc}"})

    sitemap_url_set = set(sitemap_urls)
    feed_url_set = {str(item.get("url", "")).split("#", 1)[0].rstrip("/") for item in entries if item.get("url")}
    missing_from_sitemap = sorted(feed_url_set - sitemap_url_set) if sitemap_urls and not is_sitemap_index else []
    if sitemap_urls and not is_sitemap_index:
        checks.append({"name": "feed_permalink_coverage_in_sitemap",
                       "ok": not missing_from_sitemap,
                       "feed_urls": len(feed_url_set),
                       "missing_count": len(missing_from_sitemap)})
        for missing_url in missing_from_sitemap:
            findings.append({"severity": "MEDIUM", "code": "FEED_URL_NOT_IN_SITEMAP",
                             "message": "Public feed permalink was not found in the sitemap response.",
                             "url": missing_url})

    latest_updated = max((x["updated"] for x in entries if x["updated"]), default="")
    latest_published = max((x["published"] for x in entries if x["published"]), default="")
    # This is a public-feed audit, not evidence of Google crawling or indexing.
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blog_url": base,
        "audit_scope": "Public HTTP endpoints, Blogger feed metadata, exact normalized title duplicates and basic content-length flags.",
        "important_limit": "This report does not measure Googlebot crawl, indexing, search impressions, or clicks. Use Search Console for those metrics.",
        "summary": {
            "posts_in_feed": len(entries),
            "sitemap_urls": len(sitemap_urls),
            "internal_links_between_posts": internal_link_count,
            "posts_without_internal_links": len(posts_without_internal_links),
            "feed_urls_missing_from_sitemap": len(missing_from_sitemap),
            "checks_passed": sum(1 for x in checks if x.get("ok")),
            "checks_total": len(checks),
            "high_findings": sum(1 for x in findings if x["severity"] == "HIGH"),
            "medium_findings": sum(1 for x in findings if x["severity"] == "MEDIUM"),
            "latest_published_at": latest_published,
            "latest_updated_at": latest_updated,
        },
        "checks": checks,
        "findings": findings,
        "posts_without_internal_links": posts_without_internal_links,
        "feed_urls_missing_from_sitemap": missing_from_sitemap,
        "posts": entries,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Blogger SEO Technical Snapshot",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Blog: {base}",
        f"- Posts in public feed: {len(entries)}",
        f"- URLs found in sitemap: {len(sitemap_urls)}",
        f"- Internal links between known posts: {internal_link_count}",
        f"- Posts without detected internal links: {len(posts_without_internal_links)}",
        f"- Feed URLs missing from sitemap response: {len(missing_from_sitemap)}",
        f"- Latest published timestamp in feed: {latest_published or 'not available'}",
        f"- Latest updated timestamp in feed: {latest_updated or 'not available'}",
        f"- Findings: {len(findings)} (high={report['summary']['high_findings']}, medium={report['summary']['medium_findings']})",
        "",
        "> This snapshot does not establish when Google last crawled or indexed any page. Check Search Console URL Inspection, Page indexing and Performance reports.",
        "",
        "## Endpoint checks",
        "",
    ]
    for item in checks:
        lines.append(f"- {'PASS' if item.get('ok') else 'FAIL'} — {item['name']}: HTTP {item.get('status', 'n/a')}; {item.get('url', '')}")
    lines += ["", "## Findings", ""]
    if not findings:
        lines.append("No automated findings. This is not a guarantee of indexability or content quality.")
    else:
        for item in findings:
            lines.append(f"- **{item['severity']} / {item['code']}** — {item['message']} {item.get('url', '')}")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if result["summary"]["high_findings"]:
        sys.exit(1)
