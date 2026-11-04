from __future__ import annotations
import json, os, re, unicodedata
from blogger_publisher import blog_id, service

BLOG_URL = os.getenv("BLOGGER_URL", "https://askmahmoudkhyrat.blogspot.com/").strip().rstrip("/")
BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "").strip()
TITLE = "هوية اسأل محمود"
PREFERRED_URL = BLOG_URL + "/p/blog-page_03.html"

def norm(value):
    value = unicodedata.normalize("NFKC", str(value or "")).replace("\u0640", "")
    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)
    return re.sub(r"\s+", " ", value).strip().casefold()

def all_pages(api, bid):
    items, token = [], None
    while True:
        args = {"blogId": bid, "maxResults": 100, "fetchBodies": True}
        if token: args["pageToken"] = token
        data = api.pages().list(**args).execute()
        items.extend(data.get("items", []) or [])
        token = data.get("nextPageToken")
        if not token: return items

def main():
    api = service()
    bid = BLOG_ID or blog_id(api, BLOG_URL)
    pages = all_pages(api, bid)
    matches = [p for p in pages if norm(p.get("title")) == norm(TITLE)]
    if not matches:
        raise RuntimeError("No identity page found; refusing to create or delete anything.")
    preferred = [p for p in matches if str(p.get("url", "")).rstrip("/") == PREFERRED_URL]
    keep = preferred[0] if preferred else sorted(matches, key=lambda p: int(p.get("id", "0")))[0]
    keep_id = str(keep.get("id", "")).strip()
    if not keep_id: raise RuntimeError("Identity page id missing; cleanup aborted.")
    removed = []
    for page in matches:
        page_id = str(page.get("id", "")).strip()
        if page_id and page_id != keep_id:
            api.pages().delete(blogId=bid, pageId=page_id).execute()
            removed.append({"id": page_id, "url": page.get("url", "")})
    remaining = [p for p in all_pages(api, bid) if norm(p.get("title")) == norm(TITLE)]
    if len(remaining) != 1 or str(remaining[0].get("id", "")) != keep_id:
        raise RuntimeError("Post-cleanup verification failed: " + json.dumps(remaining, ensure_ascii=False))
    report = {"kept": remaining[0].get("url"), "removed": removed, "remaining_identity_pages": len(remaining)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n## Identity-page cleanup\n\n")
            f.write(f"- Kept: {report['kept']}\n- Removed duplicates: {len(removed)}\n- Remaining: 1\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
