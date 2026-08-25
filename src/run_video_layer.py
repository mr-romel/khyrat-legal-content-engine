from __future__ import annotations

import os

from config import load_video_config
from sheets import create_service
from video_layer import prepare_due_video_tasks


def main() -> None:
    config = load_video_config()
    sheet_range = os.getenv("GOOGLE_SHEET_RANGE", config["sheet_range"]).strip() or config["sheet_range"]
    service = create_service(config["service_account_info"])
    prepared = prepare_due_video_tasks(
        service=service,
        spreadsheet_id=config["sheet_id"],
        sheet_range=sheet_range,
    )
    print(f"Video Layer: prepared {prepared} Gemini Notebook task(s).")


if __name__ == "__main__":
    main()
