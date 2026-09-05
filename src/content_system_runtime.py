from __future__ import annotations

import run_main
from content_planner import classify
from content_system import ensure_system_sheets, record_publication_intelligence
from post_bank import get_bank_rows
from sheets import create_service


_original_process_row = run_main.production_main.process_row


def _process_with_intelligence(*, service, config, sheet_name, row_number, row, current):
    _original_process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)
    try:
        bank_rows = get_bank_rows(service, config["sheet_id"])
        source_id = str(row.get("ID", "") or "").strip()
        matches = [r for r in bank_rows if source_id and str(r.get("Source Row ID", "")).strip() == source_id]
        latest = matches[-1] if matches else (bank_rows[-1] if bank_rows else {})
        facebook_id = str(latest.get("Facebook Post ID", "")).strip()
        linkedin_id = str(latest.get("LinkedIn Post ID", "")).strip()
        post_id = facebook_id or linkedin_id
        if not post_id:
            print("Content system: no published post ID; skipping lineage record.")
            return
        topic = str(latest.get("الموضوع", row.get("الموضوع", ""))).strip()
        angle = str(run_main._latest_editorial.get("angle", "") or latest.get("زاوية المحتوى", "")).strip()
        pillar, objective = classify(topic, str(latest.get("المحتوى", "")))
        record_publication_intelligence(
            service,
            config["sheet_id"],
            source_row_id=source_id,
            topic=topic,
            angle=angle or pillar,
            objective=objective,
            platform="Facebook + LinkedIn",
            post_id=post_id,
        )
    except Exception as exc:
        print(f"Content system runtime failed (non-blocking): {exc}")


run_main.production_main.process_row = _process_with_intelligence


def main() -> None:
    config = run_main.production_main.load_config()
    service = create_service(config["service_account_info"])
    ensure_system_sheets(service, config["sheet_id"])
    run_main._smart_main()


if __name__ == "__main__":
    main()
