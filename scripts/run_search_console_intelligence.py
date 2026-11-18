from __future__ import annotations

import json
import os

from search_console_intelligence import run


def main() -> int:
    days = max(7, min(int(os.getenv("SEARCH_CONSOLE_DAYS", "28")), 90))
    result = run(days=days)
    print("FREE_GOOGLE_SEARCH_CONSOLE_SYNC=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
