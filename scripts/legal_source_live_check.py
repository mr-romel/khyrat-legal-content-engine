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
            print(f"RESULT: BLOCKED — no primary/official source was retrieved and verified in this run for: {topic}", flush=True)
            continue

        blocks = re.split(r"(?m)^SOURCE\s+\d+\s*$", packet)
        sources = []
        primary_types = {"current_legislation_source", "judgment_or_principle", "official_government_source"}
        for block in blocks[1:]:
            source_type = re.search(r"(?m)^Type:\s*(\S+)", block)
            match = re.search(r"(?m)^URL:\s*(https://\S+)", block)
            evidence = re.search(r"(?m)^VERIFIED SOURCE TEXT \(retrieved\):\s*(.{30,})$", block)
            if source_type and source_type.group(1) in primary_types and match and evidence:
                sources.append((source_type.group(1), match.group(1).rstrip(").,;")))
        if not sources:
            failures.append(topic)
            print("RESULT: BLOCKED — packet had no parseable primary/official source record.", flush=True)
            continue
        print(f"RESULT: VERIFIED PRIMARY/OFFICIAL SOURCES — {len(sources)} record(s) retrieved in this run.", flush=True)
        for source_type, url in sources:
            print(f"VERIFIED_SOURCE_TYPE: {source_type}", flush=True)
            print(f"VERIFIED_URL: {url}", flush=True)

    if failures:
        print("\nLIVE LEGAL SOURCE CHECK FAILED: " + " | ".join(failures), flush=True)
        return 1
    print("\nLEGAL SOURCE RECOVERY CHECK PASSED: both current queue topics have retrieved primary/official source records.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
