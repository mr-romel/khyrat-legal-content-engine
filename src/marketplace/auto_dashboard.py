"""Run the Marketplace dashboard with non-blocking public-opportunity sync."""
from __future__ import annotations

import json
import threading
import time
import webbrowser
from urllib.request import Request, urlopen

from marketplace.discovery import merge_discoveries
from marketplace_mvp import load_state, save_state
from marketplace.pipeline import ingest_mostaql_opportunity
from marketplace.pro_dashboard_content import main

FEED_URL = "https://raw.githubusercontent.com/mr-romel/khyrat-legal-content-engine/main/marketplace_data/discovered_opportunities.json"
INTERVAL_SECONDS = 600
DASHBOARD_URL = "http://127.0.0.1:8766/"


def _offer(item: dict) -> str:
    return (
        "مرحباً، قرأت تفاصيل المشروع وأرى أن المطلوب يتوافق مباشرة مع خبرتي في الأعمال القانونية، "
        "خصوصاً تحليل المخاطر وصياغة ومراجعة المستندات.\n\n"
        "سأبدأ بفهم المتطلبات وتحديد النقاط القانونية المؤثرة، ثم أقدم الملاحظات والصياغات المقترحة "
        "بشكل واضح ومنظم، مع الالتزام بنطاق العمل المتفق عليه.\n\n"
        f"المدة المقترحة: {item.get('suggested_days', 3)} أيام. "
        f"والميزانية المقترحة: ${item.get('suggested_price_usd', 5)}.\n\n"
        "إذا أرسلت التفاصيل الأساسية أو نموذج المستند، أستطيع تحديد نطاق العمل النهائي بدقة قبل البدء."
    )


def sync_feed() -> int:
    request = Request(FEED_URL, headers={"User-Agent": "KhyratMarketplaceDashboard/2.1"})
    with urlopen(request, timeout=15) as response:
        remote = json.loads(response.read().decode("utf-8"))
    state = load_state()
    opportunities = state.setdefault("opportunities", [])
    known = {str(x.get("source_url")) for x in opportunities if x.get("source_url")}
    added = 0
    for item in merge_discoveries([], remote):
        source_url = str(item.get("source_url", ""))
        if not source_url or source_url in known:
            continue
        created = ingest_mostaql_opportunity(
            state, str(item.get("title", "")), str(item.get("description", "")), source_url
        )
        created["discovery_score"] = int(item.get("discovery_score", 0))
        created["suggested_price_usd"] = 5
        created["suggested_days"] = 3
        created["offer"] = _offer(created)
        created["status"] = created["lifecycle"] = "OFFER_READY"
        known.add(source_url)
        added += 1
    if added:
        save_state(state)
    return added


def _background_sync() -> None:
    while True:
        try:
            added = sync_feed()
            print(f"[marketplace] discovery sync: +{added} new opportunities", flush=True)
        except Exception as exc:
            print(f"[marketplace] discovery sync skipped: {exc}", flush=True)
        time.sleep(INTERVAL_SECONDS)


def _open_browser() -> None:
    time.sleep(1.5)
    try:
        webbrowser.open(DASHBOARD_URL, new=2)
    except Exception:
        pass


def start() -> None:
    threading.Thread(target=_background_sync, daemon=True, name="marketplace-discovery").start()
    threading.Thread(target=_open_browser, daemon=True, name="marketplace-browser").start()
    print(f"[marketplace] dashboard: {DASHBOARD_URL}", flush=True)
    print("[marketplace] discovery runs in the background every 10 minutes.", flush=True)
    main()


if __name__ == "__main__":
    start()
