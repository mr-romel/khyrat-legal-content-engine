# One-time Blogger demand article run

This marker exists to trigger the independent daily legal search-demand article workflow once on 2026-10-09. The worker is idempotent for the Cairo calendar date and records the chosen query, observed demand signals, keywords, article title, and publication URL in data/blogger_keyword_map.json.

Retry trigger after reducing browser install time: 2026-10-09.
