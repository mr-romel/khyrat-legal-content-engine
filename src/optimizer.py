from __future__ import annotations

from collections import defaultdict

from content_planner import classify
from sheets import get_values
from telegram_bot import notify


def run(*, service, spreadsheet_id: str) -> None:
    values = get_values(service, spreadsheet_id, "Performance!A:J")
    if len(values) <= 1:
        return

    scores = defaultdict(list)
    for raw in values[1:]:
        padded = list(raw) + [""] * (10 - len(raw))
        topic = padded[1]
        try:
            fb_comments = int(padded[3] or 0)
            fb_reactions = int(padded[4] or 0)
            fb_shares = int(padded[5] or 0)
            li_comments = int(padded[7] or 0)
            li_likes = int(padded[8] or 0)
        except ValueError:
            continue
        pillar, objective = classify(topic)
        score = fb_comments * 3 + fb_reactions + fb_shares * 4 + li_comments * 3 + li_likes
        scores[(pillar, objective)].append(score)

    ranked = sorted(
        ((key, sum(values) / len(values), len(values)) for key, values in scores.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return

    lines = ["📊 Monthly Content Intelligence", ""]
    for (pillar, objective), score, count in ranked[:5]:
        lines.append(f"• {pillar} / {objective}: average score {score:.1f} ({count} posts)")
    lines.append("")
    lines.append("Recommendation: increase the share of the highest-performing pillars gradually; do not repeat the same topic verbatim.")
    notify("\n".join(lines))
