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


## Implementation update — 2026-11-02
The repository already contained a direct Google Search Console API client and a scheduled Blogger Organic Growth Loop. The growth loop was extended rather than introducing Windsor.ai as a required dependency.

Implemented:
- Equal-length current-versus-previous Search Console windows for both page and query/page dimensions.
- Period comparison metrics for clicks, impressions and CTR.
- Persistent, idempotent Google Sheets tabs: `SEOOpportunityLog` and `SEOGrowthRuns`.
- Evidence-linked opportunity rows with observed query, page, clicks, impressions, CTR, average position, legal cluster, intent, opportunity type, priority score, recommended action, baseline values, and period deltas.
- Stable SHA-256 IDs to prevent duplicate ledger rows on workflow retries.
- A guard that logs empty source runs as `EMPTY_SOURCE` rather than presenting empty connector data as zero traffic.
- Query CSV artifact in addition to the existing page CSV and JSON growth snapshot.
- Regression tests for period comparison, query evidence and baseline deltas.

Existing workflow `.github/workflows/blogger-growth-loop.yml` runs daily in Africa/Cairo and is configured for push-triggered execution when the growth-loop runner changes. It runs tests, the Blogger technical audit, direct Google Search Console API extraction, and the Search GEO backfill.

## Execution boundary
A GitHub commit is not proof that the Actions workflow completed, and a successful workflow is not proof of search growth. The workflow must complete with non-empty API rows and successfully write to the connected Google Sheet before the live data pipeline is considered operational. If the API returns an access error, grant the service-account email from the configured Google service-account JSON read access to the exact Search Console property. Do not paste private keys or tokens into chat.

## Follow-up hardening — 2026-11-02

A further integration review found a configuration mismatch in the Search GEO backfill: the main growth runner accepted either `GOOGLE_SHEET_ID` or the verified `GOOGLE_SHEET_URL`, while `scripts/run_search_geo.py` required only the ID secret. This could allow the Search Console ledger step to run and then fail at the GEO backfill when deployments store only the spreadsheet URL.

Corrected the GEO runner to use the shared `_sheet_id()` resolver, aligned its default content range with the live sheet schema (`Content!A:BG`), and passed `GOOGLE_SHEET_URL` into the GitHub Actions environment. Added tests for URL fallback and explicit-ID precedence, and included those tests in the organic-growth workflow and its push path filters.

Verification boundary: the files and workflow configuration are committed, but this session has not obtained a GitHub Actions run result or a live Google API execution result. Therefore tests, Search Console extraction, and Google Sheets writes remain unverified until the workflow produces a successful run and its artifact/logs are inspected.
