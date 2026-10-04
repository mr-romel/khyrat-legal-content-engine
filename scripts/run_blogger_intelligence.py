from __future__ import annotations
import os,sys
sys.path.insert(0,"src")
from search_console_intelligence import run as run_search
from blogger_intelligence import enrich_live_posts

def main()->int:
    stats=run_search(days=int(os.getenv("SEARCH_CONSOLE_DAYS","28")))
    dry=os.getenv("BLOGGER_INTERNAL_LINK_WRITE","false").lower() not in {"1","true","yes","on"}
    links=enrich_live_posts(dry_run=dry)
    print("Search Console rows={} opportunities={} refresh={}".format(stats["rows"],stats["opportunities"],stats["refresh_items"]))
    print("Internal links posts={} updated={} dry_run={}".format(links["posts"],links["updated"],dry))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
