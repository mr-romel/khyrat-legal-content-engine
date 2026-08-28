from __future__ import annotations

from config import load_config
from pipeline import process_row
from sheets import create_service, ensure_headers, get_values, row_to_dict
from utils import now_cairo, parse_date, parse_time, sheet_name_from_range


def _is_due(row: dict[str, str], current) -> bool:
    status = str(row.get("الحالة", "READY")).strip().upper()
    if status not in {"READY", "FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"}:
        return False
    target_date = parse_date(row.get("تاريخ النشر", ""))
    target_time = parse_time(row.get("ساعة النشر", ""))
    if target_date is None or target_time is None:
        return False
    target = current.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    return 0 <= (current - target).total_seconds() < 3600 and current.date() >= target_date


def _failed_retry(row: dict[str, str]) -> bool:
    return str(row.get("الحالة", "")).strip().upper() in {"FAILED", "PARTIAL_FAILED", "READY_FOR_SOCIAL_PUBLISH"} and bool(row.get("الموضوع", "").strip())


def main() -> None:
    print("=" * 70)
    print("KHYRAT LEGAL CONTENT ENGINE - V2 SMART SOCIAL PIPELINE")
    print("=" * 70)
    current = now_cairo()
    print(f"Current Cairo time: {current.isoformat()}")
    config = load_config()
    service = create_service(config["service_account_info"])
    sheet_name = sheet_name_from_range(config["sheet_range"])
    ensure_headers(service, config["sheet_id"], sheet_name)
    values = get_values(service, config["sheet_id"], config["sheet_range"])
    if not values:
        print("No rows found.")
        return
    rows = [row_to_dict(row) for row in values[1:]]
    candidates = [(index, row) for index, row in enumerate(rows, start=2) if _is_due(row, current)]
    if not candidates:
        candidates = [(index, row) for index, row in enumerate(rows, start=2) if _failed_retry(row)][:1]
    if not candidates:
        print("No due rows found.")
        return
    row_number, row = candidates[0]
    process_row(service=service, config=config, sheet_name=sheet_name, row_number=row_number, row=row, current=current)


if __name__ == "__main__":
    main()
