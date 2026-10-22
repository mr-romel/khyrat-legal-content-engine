from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _number(value: object) -> float:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", str(value or "").casefold())


def _canonical_url(value: str) -> str:
    p = urlsplit(str(value or "").strip())
    if not p.scheme or not p.netloc:
        return str(value or "").strip().rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


def _field(row: dict[str, str], *names: str) -> str:
    normalized = {_key(k): str(v or "").strip() for k, v in row.items()}
    for name in names:
        if _key(name) in normalized:
            return normalized[_key(name)]
    return ""


def read_search_console_csv(path: str) -> list[dict]:
    """Read a Google Search Console Pages export (UTF-8 BOM supported)."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        url = _field(row, "Top pages", "Pages", "Page", "URL")
        if not url.startswith(("http://", "https://")):
            continue
        result.append({"url": _canonical_url(url), "clicks": _number(_field(row, "Clicks")),
                       "impressions": _number(_field(row, "Impressions")),
                       "ctr": _number(_field(row, "CTR")),
                       "position": _number(_field(row, "Position", "Average position"))})
    return result


def prioritize(audit: dict, performance: list[dict], limit: int = 100) -> dict:
    posts = audit.get("posts", [])
    by_url = {_canonical_url(p.get("url", "")): p for p in posts if p.get("url")}
    findings_by_url: dict[str, list[str]] = {}
    for finding in audit.get("findings", []):
        url = _canonical_url(finding.get("url", ""))
        if url:
            findings_by_url.setdefault(url, []).append(str(finding.get("code", "AUDIT_FINDING")))
    metrics_by_url = {_canonical_url(row["url"]): row for row in performance}
    priorities = []
    for url, post in by_url.items():
        metrics = metrics_by_url.get(url, {"clicks": 0.0, "impressions": 0.0, "ctr": 0.0, "position": 0.0})
        clicks, impressions, ctr, position = (metrics[k] for k in ("clicks", "impressions", "ctr", "position"))
        ctr_pct = ctr * 100 if 0 < ctr <= 1 else ctr
        opportunity, reasons = 0.0, []
        if impressions >= 100 and ctr_pct < 3:
            opportunity += min(impressions / 100, 30) * (3 - ctr_pct + 1)
            reasons.append("HIGH_IMPRESSIONS_LOW_CTR")
        if impressions >= 50 and 4 <= position <= 20:
            opportunity += min(impressions / 100, 30) * 2
            reasons.append("RANKING_NEAR_PAGE_ONE")
        if url in findings_by_url:
            opportunity += 8 * len(findings_by_url[url])
            reasons.extend(findings_by_url[url])
        if not post.get("internal_links_to_known_posts"):
            opportunity += 5
            reasons.append("ADD_CONTEXTUAL_INTERNAL_LINKS")
        if url not in metrics_by_url:
            reasons.append("NO_SEARCH_CONSOLE_ROW")
        priorities.append({"title": post.get("title", ""), "url": post.get("url", ""),
                           "clicks": int(clicks), "impressions": int(impressions),
                           "ctr_percent": round(ctr_pct, 2), "average_position": round(position, 2),
                           "priority_score": round(opportunity, 2),
                           "reasons": list(dict.fromkeys(reasons)), "suggested_internal_links": []})
    tokens = {url: {t for t in re.findall(r"[\w\u0600-\u06ff]+", str(post.get("title", "")).casefold()) if len(t) > 2}
              for url, post in by_url.items()}
    for item in priorities:
        source = _canonical_url(item["url"])
        candidates = []
        for target, target_post in by_url.items():
            if target == source:
                continue
            overlap = tokens.get(source, set()) & tokens.get(target, set())
            if overlap:
                candidates.append((len(overlap), target_post.get("title", ""), target_post.get("url", "")))
        candidates.sort(key=lambda x: (-x[0], x[1]))
        item["suggested_internal_links"] = [{"title": title, "url": target_url, "shared_title_terms": score}
                                            for score, title, target_url in candidates[:3]]
    priorities.sort(key=lambda item: (-item["priority_score"], -item["impressions"], -item["clicks"]))
    return {"note": "GSC page-level export + public Blogger audit. Missing rows do not prove zero traffic; validate edits before publishing.",
            "pages_with_search_console_data": sum(1 for p in priorities if "NO_SEARCH_CONSOLE_ROW" not in p["reasons"]),
            "pages_in_audit": len(priorities), "priorities": priorities[:max(1, limit)]}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Prioritize Blogger articles using GSC Pages CSV and SEO audit JSON.")
    parser.add_argument("--gsc-csv", required=True, help="Search Console Performance > Pages CSV export")
    parser.add_argument("--audit-json", default="artifacts/seo-audit/report.json")
    parser.add_argument("--output", default="artifacts/seo-audit/content-priorities.json")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8"))
    result = prioritize(audit, read_search_console_csv(args.gsc_csv))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("pages_with_search_console_data", "pages_in_audit")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
