from __future__ import annotations
import os,sys
sys.path.insert(0,"src")
from search_console_intelligence import run as run_search
from blogger_intelligence import enrich_live_posts

def main()->int:
    # Search Console is intelligence only. Its API availability must never
    # prevent Blogger internal-link enrichment from running.
    try:
        stats=run_search(days=int(os.getenv("SEARCH_CONSOLE_DAYS","28")))
    except Exception as exc:
        stats={"rows":0,"opportunities":0,"refresh_items":0}
        print(f"Search Console intelligence unavailable; Blogger enrichment continues: {exc}")
    dry=os.getenv("BLOGGER_INTERNAL_LINK_WRITE","false").lower() not in {"1","true","yes","on"}
    try:
        links=enrich_live_posts(dry_run=dry)
    except Exception as exc:
        links={"posts":0,"updated":0}
        print(f"Blogger internal-link enrichment unavailable: {exc}")
    print("Search Console rows={} opportunities={} refresh={}".format(stats["rows"],stats["opportunities"],stats["refresh_items"]))
    print("Internal links posts={} updated={} dry_run={}".format(links["posts"],links["updated"],dry))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
