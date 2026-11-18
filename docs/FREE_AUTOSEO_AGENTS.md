# Free AutoSEO / GEO operating plan

This plan requires no paid API or paid SaaS. It uses Python, public Blogger endpoints, existing Search Console integration when configured, and GitHub Actions only within included account allowances.

## Implemented workflow
- Technical audit: homepage, Blogger feed, sitemap, robots.txt, duplicate-title signals, content-length signals, internal-link signals and sitemap coverage. It does not claim Google indexed any page.
- Search opportunity prioritization: the repository queries the official Google Search Console API directly (service-account OAuth), scores high-impression/low-CTR pages and positions 4-20, and writes opportunities to Google Sheets. No Windsor.ai connector or paid data intermediary is required. Search Console property access is required.
- Editorial action planning: prioritize observed opportunities for human review. Do not fabricate legal sources or automatically rewrite/delete/publish legal content.
- GEO readiness: use clear page titles, direct answers, author/source provenance and useful question structure. No AI-search placement is guaranteed.
- Measurement: preserve a dated technical audit report as a GitHub Actions artifact; compare later reports and Search Console periods before claiming improvements.

## Zero-cost and safety rules
- No paid API dependencies, subscriptions, or required billing account are added.
- No automatic mass edits/deletions. Duplicate candidates remain findings for review unless the existing verified cleanup flow is explicitly run.
- Keep credentials in repository secrets; never commit credentials or tokens.
- If Search Console credentials or property permission are absent, the public technical audit still runs; live ranking metrics cannot be claimed. The native Search Console API has no usage charge, subject to Google's published quotas.
- Respect Google quotas and GitHub Actions included limits. This adds no paid service but cannot guarantee unrelated usage on an account never incurs charges.
- Claim ranking gains only when supported by dated Search Console evidence.


## Native Google Search Console replacement for Windsor.ai
- Workflow: `.github/workflows/free-google-search-console.yml` (daily + manual dispatch).
- Runner: `scripts/run_search_console_intelligence.py`.
- Data source: Google's official Search Console API directly; no Windsor.ai account, paid connector, trial, or third-party SaaS.
- Required existing secrets: `GOOGLE_SERVICE_ACCOUNT_JSON` (or `GOOGLE_CREDENTIALS`) and `GOOGLE_SHEET_ID`.
- Property: `SEARCH_CONSOLE_SITE_URL`; defaults to the Blogger URL already used by this repository.
- The Google service-account email must already have access to the Search Console property. The workflow cannot grant itself that permission.
- Metrics: query, page, clicks, impressions, CTR, average position, intent, and opportunity recommendations.
- This is genuinely free at the Google API layer; GitHub Actions remains subject to the repository owner's included Actions allowance.
