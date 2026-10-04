from __future__ import annotations
import os,sys
sys.path.insert(0,"src")
from blogger_pages import upsert_pages
if __name__=="__main__":
    dry=os.getenv("BLOGGER_DRY_RUN","false").lower() in {"1","true","yes","on"}
    print(upsert_pages(dry_run=dry))
