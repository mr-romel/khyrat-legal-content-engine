from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_research import has_verified_legal_source, research_legal_topic


TOPICS = (
    "الوظيفة العامة والتعيين",
    "امتناع الإدارة عن اتخاذ القرار",
)


def main() -> int:
    failures = []
    for topic in TOPICS:
        print(f"\n=== LIVE LEGAL SOURCE CHECK: {topic} ===", flush=True)
        packet = research_legal_topic(topic)
        if not has_verified_legal_source(packet):
            failures.append(topic)
            print(f"RESULT: BLOCKED — no verified source passed retrieval or curated fallback validation for: {topic}", flush=True)
            continue

        blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", packet)
        urls = []
        for block in blocks[1:]:
            match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
            evidence = re.search(r"(?m)^VERIFIED SOURCE TEXT \(retrieved\):\s*(.{30,})$", block)
            if match and evidence:
                urls.append(match.group(1).rstrip(").,;"))
        if not urls:
            failures.append(topic)
            print("RESULT: BLOCKED — packet had no parseable verified source record.", flush=True)
            continue
        print(f"RESULT: VERIFIED SOURCE RECORDS — {len(urls)} source record(s); inspect packet provenance to distinguish live retrieval from curated offline evidence", flush=True)
        for url in urls:
            print(f"VERIFIED_URL: {url}", flush=True)

    if failures:
        print("\nLIVE LEGAL SOURCE CHECK FAILED: " + " | ".join(failures), flush=True)
        return 1
    print("\nLEGAL SOURCE RECOVERY CHECK PASSED: both current queue topics have verified source records; provenance labels distinguish live retrieval from curated offline evidence.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
