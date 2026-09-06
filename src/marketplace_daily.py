"""CLI for generating the Marketplace daily execution plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from marketplace.daily_ops import build_daily_plan, task_counts
from marketplace_mvp import load_state, save_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Marketplace daily execution plan")
    parser.add_argument("--stale-days", type=int, default=14)
    parser.add_argument("--output", default="marketplace_data/daily_plan.json")
    args = parser.parse_args()

    from datetime import datetime

    state = load_state()
    plan = build_daily_plan(state, datetime.now().astimezone(), stale_days=args.stale_days)
    save_state(state)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = task_counts(plan)
    print("خطة التنفيذ اليومية لسوق الخدمات")
    print(f"متابعات مستحقة: {counts['FOLLOW_UP']}")
    print(f"عروض جاهزة للتقديم: {counts['SUBMIT']}")
    print(f"فرص تحتاج مراجعة: {counts['REVIEW']}")
    print(f"فرص منتهية تلقائياً: {plan['expired_count']}")
    print(f"الفرص المفتوحة: {plan['total_open']}")
    print(f"تم حفظ الخطة في: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
