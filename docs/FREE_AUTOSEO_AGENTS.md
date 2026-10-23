# Free AutoSEO / GEO operating plan

This plan requires no paid API or paid SaaS. It uses Python, public Blogger endpoints, existing Search Console integration when configured, and GitHub Actions only within included account allowances.

## Implemented workflow
- Technical audit: homepage, Blogger feed, sitemap, robots.txt, duplicate-title signals, content-length signals, internal-link signals and sitemap coverage. It does not claim Google indexed any page.
- Search opportunity prioritization: existing Search Console modules score high-impression low-CTR pages and pages around positions 4-20. Search Console access and site property configuration are required for live metrics.
- Editorial action planning: prioritize observed opportunities for human review. Do not fabricate legal sources or automatically rewrite/delete/publish legal content.
- GEO readiness: use clear page titles, direct answers, author/source provenance and useful question structure. No AI-search placement is guaranteed.
- Measurement: preserve a dated technical audit report as a GitHub Actions artifact; compare later reports and Search Console periods before claiming improvements.

## Zero-cost and safety rules
- No paid API dependencies, subscriptions, or required billing account are added.
- No automatic mass edits/deletions. Duplicate candidates remain findings for review unless the existing verified cleanup flow is explicitly run.
- Keep credentials in repository secrets; never commit credentials or tokens.
- If Search Console credentials are absent, the public technical audit still runs; live ranking metrics cannot be claimed.
- Respect Google quotas and GitHub Actions included limits. This adds no paid service but cannot guarantee unrelated usage on an account never incurs charges.
- Claim ranking gains only when supported by dated Search Console evidence.
