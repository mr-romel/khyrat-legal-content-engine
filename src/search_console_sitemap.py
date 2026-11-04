from __future__ import annotations
import json, os
from datetime import date, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip()
SITEMAP_URL = os.getenv("BLOGGER_SITEMAP_URL", BLOG_URL.rstrip("/") + "/sitemap.xml")
SCOPES = ["https://www.googleapis.com/auth/webmasters"]
IDENTITY_URL = BLOG_URL.rstrip("/") + "/p/blog-page_03.html"
ABOUT_URL = BLOG_URL.rstrip("/") + "/p/blog-page.html"
INSPECT_URLS = [BLOG_URL, IDENTITY_URL, ABOUT_URL]
NAME_VARIANTS = ["محمود خيرت المحامي", "محمود خيرت", "محمود خيرت رجب", "اسأل محمود", "إسأل محمود", "اسال محمود", "مدونة اسأل محمود", "قناة اسأل محمود"]
CONTENT_GROUPS = ["قانون الشركات", "قانون العمل", "العقود التجارية", "مراجعة عقود الشركات", "حقوق صاحب العمل", "إنهاء عقد العمل"]

def safe_call(label, callback):
    try: return callback()
    except Exception as exc:
        print(f"WARNING: {label} unavailable: {type(exc).__name__}: {exc}")
        return None

def inspect_urls(client):
    results = []
    for url in INSPECT_URLS:
        data = safe_call(f"URL Inspection {url}", lambda url=url: client.urlInspection().index().inspect(body={"inspectionUrl": url, "siteUrl": BLOG_URL}).execute())
        if data is None:
            results.append({"url": url, "status": "inspection_unavailable"})
            continue
        index = data.get("inspectionResult", {}).get("indexStatusResult", {})
        results.append({"url": url, "verdict": index.get("verdict"), "coverageState": index.get("coverageState"), "indexingState": index.get("indexingState"), "robotsTxtState": index.get("robotsTxtState"), "pageFetchState": index.get("pageFetchState"), "googleCanonical": index.get("googleCanonical"), "userCanonical": index.get("userCanonical"), "lastCrawlTime": index.get("lastCrawlTime"), "referringUrls": index.get("referringUrls", [])})
    return results

def _query_phrase(client, phrase, start, end):
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
            "dimensions": ["query"],
            "dimensionFilterGroups": [{"filters": [{"dimension": "query", "operator": "contains", "expression": phrase}]}],
            "rowLimit": 100}
    data = safe_call(f"Search Analytics {phrase}", lambda: client.searchanalytics().query(siteUrl=BLOG_URL, body=body).execute())
    rows = (data or {}).get("rows", []) or []
    clicks = sum(int(row.get("clicks", 0)) for row in rows)
    impressions = sum(int(row.get("impressions", 0)) for row in rows)
    weighted = sum(float(row.get("position", 0)) * int(row.get("impressions", 0)) for row in rows)
    return {"phrase": phrase, "clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions if impressions else 0,
            "averagePosition": weighted / impressions if impressions else None,
            "dataAvailable": data is not None,
            "matchingQueries": [{"query": (row.get("keys") or [""])[0], "clicks": row.get("clicks", 0),
                                 "impressions": row.get("impressions", 0), "ctr": row.get("ctr", 0),
                                 "position": row.get("position")} for row in rows]}


def query_name_visibility(client):
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=27)
    return {"startDate": start.isoformat(), "endDate": end.isoformat(),
            "phrases": [_query_phrase(client, phrase, start, end) for phrase in NAME_VARIANTS],
            "contentGroups": [_query_phrase(client, phrase, start, end) for phrase in CONTENT_GROUPS],
            "measurementNotes": [
                "Search Console query rows may omit anonymized low-volume searches.",
                "Contains filters overlap; phrase totals are separate views and must not be added together.",
                "The reporting window excludes the latest two days because recent Search Analytics data may be incomplete.",
            ]}


def write_report(payload):
    with open("search-visibility-report.json", "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)
    lines = ["# Search visibility report", f"Period: {payload['analytics']['startDate']} to {payload['analytics']['endDate']}", "", "## Name-query performance", "| Search phrase | Clicks | Impressions | CTR | Avg. position |", "|---|---:|---:|---:|---:|"]
    for row in payload["analytics"]["phrases"]:
        pos = f"{row['averagePosition']:.1f}" if row["averagePosition"] is not None else "—"
        lines.append(f"| {row['phrase']} | {row['clicks']} | {row['impressions']} | {row['ctr']:.1%} | {pos} |")
    lines += ["", "## URL inspection", "| URL | Verdict | Coverage | Last crawl |", "|---|---|---|---|"]
    for row in payload["urlInspection"]: lines.append(f"| {row['url']} | {row.get('verdict', row.get('status', 'unknown'))} | {row.get('coverageState', '—')} | {row.get('lastCrawlTime', '—')} |")
    report = "\n".join(lines) + "\n"
    with open("search-visibility-report.md", "w", encoding="utf-8") as f: f.write(report)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f: f.write(report)

def main():
    raw = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_CREDENTIALS") or "").strip()
    if not raw: raise RuntimeError("Google service-account credentials are missing.")
    try: info = json.loads(raw)
    except json.JSONDecodeError as exc: raise RuntimeError("Google service-account credentials are not valid JSON.") from exc
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    client = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    site = client.sites().get(siteUrl=BLOG_URL).execute()
    permission = str(site.get("permissionLevel", ""))
    if permission not in {"siteOwner", "siteFullUser", "siteRestrictedUser"}: raise RuntimeError(f"Unexpected Search Console permission: {permission!r}")
    sitemaps = client.sitemaps().list(siteUrl=BLOG_URL).execute().get("sitemap", []) or []
    match = next((x for x in sitemaps if str(x.get("path", "")).rstrip("/") == SITEMAP_URL.rstrip("/")), None)
    if match is None: client.sitemaps().submit(siteUrl=BLOG_URL, feedpath=SITEMAP_URL).execute()
    verified = client.sitemaps().list(siteUrl=BLOG_URL).execute().get("sitemap", []) or []
    sitemap = next((x for x in verified if str(x.get("path", "")).rstrip("/") == SITEMAP_URL.rstrip("/")), None)
    if sitemap is None: raise RuntimeError("Search Console did not return the sitemap after submission.")
    sitemap_report = {"path": sitemap.get("path"), "lastSubmitted": sitemap.get("lastSubmitted"), "lastDownloaded": sitemap.get("lastDownloaded"), "isPending": sitemap.get("isPending"), "warnings": sitemap.get("warnings"), "errors": sitemap.get("errors")}
    payload = {"site": BLOG_URL, "permission": permission, "sitemap": sitemap_report, "urlInspection": inspect_urls(client), "analytics": query_name_visibility(client)}
    write_report(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
