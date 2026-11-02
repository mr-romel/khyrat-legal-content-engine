# SEO/GEO Search Intelligence Audit
**Run date:** 2026-11-02  
**Property configured:** https://askmahmoudkhyrat.blogspot.com/  
**Source:** Windsor.ai Search Console connector

## Executive result
The Search Console connector is present and exposes the configured Blogspot property. The field catalogue includes query, page, clicks, impressions, CTR, position, date, device, country and search type. However, data retrieval returned **0 rows** for both the last 3 months and the last 12 months. Therefore no query-level opportunity, CTR gap, page refresh candidate, topic cluster or measured performance lift can responsibly be reported from this run.

A forced refresh was also attempted but rejected because the connected Windsor.ai account is on the Trial plan: `force_refresh=partial` is unavailable. This is a connector-plan limitation, not evidence that the site has zero Google impressions.

## Verified connector state
- Connector: `searchconsole`
- Connected account: `https://askmahmoudkhyrat.blogspot.com/`
- Available dimensions/metrics include `query`, `page`, `date`, `clicks`, `impressions`, `ctr`, `position`, `device`, `country`, `search_type`.
- Last 3 months: 0 rows.
- Last 12 months: 0 rows.
- Trial plan disallows partial force refresh.

## Required unblock
1. In Search Console, verify the signed-in Google account has access to the exact Blogspot URL-prefix property shown above.
2. Confirm the property is receiving Search performance data and that the connector account points to the same property (not a different URL-prefix/domain property).
3. Re-authorize the Search Console connector if access/property selection is stale.
4. Upgrade/enable a Windsor plan that supports fresh-data refresh, or use a direct Google Search Console API integration with an authorized service account/OAuth credential.
5. Re-run a 16-month query/page export after the property and refresh path are verified. Do not treat an empty connector response as zero traffic.

## Analysis rules once data is available
- **CTR opportunities:** impressions >= 100, clicks = 0 or CTR materially below the site's comparable query/page baseline; segment by position to avoid prioritizing queries ranking too low to earn clicks.
- **Near-wins:** average position 4–20 with meaningful impressions; prioritize intent match, title/snippet clarity, and content completeness.
- **Refresh candidates:** pages with sustained impressions and declining clicks/CTR or positions, compared with the preceding period.
- **New-topic candidates:** non-branded queries with impressions but no adequate page match; cluster by legal intent and jurisdiction.
- **Cannibalization:** multiple URLs receiving impressions for the same query family.
- **GEO readiness:** answer-first summaries, explicit jurisdiction/date context, authoritative primary-law citations, definitions, structured FAQs where useful, author/reviewer attribution, and consistent entity terminology. Do not add unsupported legal claims or fabricate citations.

## Content-ledger fields to implement
`run_id`, `observed_at`, `source_property`, `query`, `target_url`, `clicks`, `impressions`, `ctr`, `avg_position`, `country`, `device`, `search_type`, `intent`, `legal_cluster`, `opportunity_type`, `priority_score`, `recommended_action`, `baseline_window`, `measurement_window`, `change_id`, `published_at`, `status`, `owner`, `result_click_delta`, `result_ctr_delta`, `result_position_delta`, `evidence_url`.

## Closed-loop operating sequence
1. Pull and retain raw Search Console query/page/day data.
2. Aggregate query and page opportunities; calculate CTR and period-over-period changes in code.
3. Deduplicate and cluster queries by legal intent, not merely shared words.
4. Score opportunities using impressions, position, CTR gap, business/legal relevance, content quality gap, and update effort.
5. Create a ledger record for every proposed change before editing.
6. Update one page or publish one cluster asset per change ID; preserve canonical URLs and avoid thin duplicate pages.
7. Record exact published URL, timestamp, changed sections, internal links and sources.
8. Compare a 28-day post-change window with a 28-day pre-change baseline (with seasonality and low-volume caveats); label results inconclusive when sample size is insufficient.
9. Feed observed outcomes back into scoring. Do not claim ranking/traffic gains from successful code runs.

## Current status
**Data extraction:** blocked by empty connector result (0 rows).  
**Opportunity analysis:** not run; no source rows.  
**SEO/GEO ledger writes:** not run; content table destination/schema not yet verified.  
**Article edits/publication:** intentionally not triggered without evidence, to avoid arbitrary edits.  
**Performance validation:** pending a non-empty Search Console export.

## Decision
Do not generate an invented keyword list or report zero traffic based on this connector response. First restore a verified, non-empty Search Console data path; then run the opportunity analysis and publish evidence-linked ledger records.
