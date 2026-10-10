# Khyrat Legal Content Engine — Project Handoff

**Repository:** https://github.com/mr-romel/khyrat-legal-content-engine  
**Branch:** `main`  
**Snapshot:** 2026-10-10 (Cairo time)  
**Purpose:** Automated Egyptian legal-content research, drafting, visual creation, social publishing/engagement, Reels, Telegram review, Blogger SEO/search-demand publishing, and marketplace workflows.

## Executive status

The project is active, but several external workflows remain sensitive to credentials and CPU/quota constraints. A successful GitHub Actions run is not evidence of an external publication unless a public URL, platform post ID, or Telegram delivery ID is logged.

### Confirmed recently
- A new Blogger demand article was published and its public Blogger feed permalink was verified:
  https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_314.html
- Article title: **كيفية التعامل مع الابتزاز الإلكتروني في مصر: الأدلة والخطوات القانونية التي يجب مراجعتها**
- Gemini free-tier quota was exhausted, but the Blogger worker used the verified-source fallback and still published.
- Blogger labels were normalized after Blogger rejected overlong combined labels.
- The Reel row-23 run did **not** deliver to Telegram. Its whiteboard FFmpeg overlay timed out because still-image inputs were looped while the output lacked a reliable duration cap. Code now adds an explicit `-t <base duration>` and `-shortest` to both normal and fallback overlay renders. This fix still requires a fresh run to prove delivery.
- Blogger REST OAuth still returns `invalid_grant: Token has been expired or revoked`. The saved Playwright UI session did publish the article above, but the UI path is a fallback, not a durable OAuth repair.

## P0: current issues and the real boundary of code-only fixes

1. **Blogger OAuth:** The current refresh token is invalid/revoked. Code cannot revive a revoked token or change Google Cloud OAuth consent-screen publishing mode. The owner must check whether the OAuth app is External + Testing, switch to Production if appropriate, re-authorize with the Blogger scope, and replace the GitHub secret `BLOGGER_OAUTH_JSON`. Never paste token JSON into chat or commit it.
2. **Reel row 23:** Prior run failed at whiteboard rendering, not Telegram. The root cause was the infinite/looped still-image inputs without a hard output duration. The renderer now caps output to the source duration. A new run must produce a playable branded MP4 and Telegram delivery confirmation before declaring resolution.
3. **Gemini 429:** Models in one project can share the same exhausted project quota. Cycling model names does not reliably restore quota. Blogger demand publishing now skips Gemini entirely when the key is absent and jumps to the source-grounded article fallback on quota errors instead of trying more models. This fallback must never invent statutory provisions or case citations.
4. **Pharaonic/stale imagery:** The generator prompt is post-derived and contemporary; the final-image QA prompt now explicitly rejects anachronistic period styling for ordinary present-day legal topics. The image generator writes a provenance sidecar containing provider/model, exact prompt, prompt hash, final image hash, and pending QA status; QA updates the sidecar when it runs. A final-image QA decision of REGENERATE now blocks that image from publication and continues with text-only fallback. QA-unavailable remains non-blocking to avoid turning provider quota outages into whole-pipeline outages. Prompt improvements are not considered proven until the exact final image is reviewed.
5. **UI-driven Blogger publishing:** Do not count a closed confirmation dialog as success. Success requires an exact-title Published row and a public permalink found from Blogger feed/dashboard evidence. Avoid Google HTML search as the primary verifier because it returned HTTP 429.
6. **Duplicate and dirty Blogger records:** Existing published posts must be reused by exact title/permalink to avoid duplicates. Untitled drafts exist; do not bulk-delete them without reviewing IDs, title/body, and state.

## Architecture map

### Main publishing and planning
- `src/run_main.py`, `src/main.py`: production engines and platform pipeline.
- `src/content_system.py`, `src/content_system_runtime.py`: content runtime/integration.
- `src/content_planner.py`, `src/social_content.py`, `src/content_style.py`, `src/content_style_v3.py`: content construction/style.
- `src/post_bank.py`, `src/topic_bank.py`, `src/topic_bank_500.py`, `src/topic_bank_expanded.py`: topic banks.
- `src/content_diversity.py`, `src/content_similarity.py`, `src/editorial_review.py`, `src/decision_engine.py`, `src/content_intelligence*.py`, `src/analytics.py`, `src/performance.py`: quality, uniqueness, intelligence and analytics.
- `src/daily_schedule.py`, `src/recycler_rules.py`, `src/monthly_recycler.py`: schedule and recycling.

### Blogger
- `src/blogger_worker.py`: publishing existing planned content.
- `src/blogger_demand_worker.py`: search-demand research and extra article.
- `src/blogger_publisher.py`: REST API/OAuth, HTML, labels, article preparation.
- `src/blogger_ui_publisher.py`: Playwright UI fallback, confirmation and permalink verification.
- `src/blogger_editor.py`, `src/blogger_seo_worker.py`, `src/blogger_intelligence.py`, `src/blogger_identity_worker.py`, `src/blogger_pages.py`, `src/blogger_pages_ui_worker.py`, `src/blogger_site_setup.py`: SEO, site identity, pages and editorial intelligence.
- State/artifacts: `data/blogger_keyword_map.json`, `generated/blogger/`.

### Images and legal research
- `src/gemini.py`: legal post and image-scene brief generation.
- `src/image_generator.py`: Cloudflare image generation, Gemini image fallback and brand overlay.
- `src/image_qa.py`: final rendered-image QA and regeneration decision.
- `src/free_media.py`: media search/fallbacks.
- `src/legal_research.py`, `src/legal_reference_registry.py`, `src/search_console_intelligence.py`, `src/search_geo.py`: legal sources and search demand.
- Image provenance is written beside the final image as `.provenance.json`; do not remove it before diagnosis.

### Reels and video
- `src/reel_pipeline.py`: end-to-end Reel generation, narration, whiteboard cards, branding and validation.
- `src/reel_publishers.py`, `src/telegram_publication.py`, `src/telegram_bot.py`, `src/telegram_control.py`: delivery/review/control.
- `src/video_layer.py`, `src/video_module/`: modular script, TTS, scene planning, renderers, whiteboard and queue.
- `generated/reels/`: generated Reel packages (runtime artifacts; not all are source-controlled).

### Engagement and other services
- `src/facebook_publisher.py`, `src/facebook_engagement_worker.py`, `src/facebook_private_reply_worker.py`: Facebook publication and engagement.
- `src/linkedin_publisher.py`, `src/linkedin_engagement.py`, `src/linkedin_engagement_worker.py`, `src/linkedin_comment_engine.py`: LinkedIn publication/engagement.
- `src/comment_engine.py`, `src/engagement_strategy.py`: cross-platform engagement.
- `src/token_manager.py`, `src/production_monitor.py`, `src/sheets.py`, `src/config.py`, `src/utils.py`: credentials/config/state/monitoring.
- `src/marketplace/`, `src/marketplace.py`, `src/marketplace_mvp.py`, `src/marketplace_daily.py`: marketplace and opportunity workflows.

## GitHub Actions workflow map

- `.github/workflows/publish-scheduled.yml`: scheduled production publisher; Reel handoff must be based on a real source artifact/row.
- `.github/workflows/quality-check.yml`: quality, architecture and regression checks.
- `.github/workflows/blogger-publisher.yml`: Blogger content publisher.
- `.github/workflows/blogger-demand-daily.yml`: daily search-demand article.
- `.github/workflows/blogger-oauth-check.yml`, `blogger-intelligence.yml`, `blogger-pages.yml`: OAuth health, intelligence and pages.
- `.github/workflows/reel-now.yml`: one-off locked-row Reel retry and Telegram review.
- `.github/workflows/reel-daily-generator.yml`, `reel-production.yml`, `reel-publish-approved.yml`: daily generation and controlled production.
- Other workflows cover Facebook/LinkedIn engagement, content intelligence, SEO/GEO, token health, Telegram control, video pilots/layers, deployments and marketplace tasks.

## Required operating rules

- **Schedule:** exactly one slot per calendar day; Cairo timezone; deterministic but variable time between 10:00 and 22:00 inclusive; no even/odd-day filter.
- **Recycling:** reuse subjects only with a genuinely new angle, objective, examples, hook or practical treatment. Avoid near-duplicates and prioritize unpublished items.
- **Publishing proof:** require a public permalink, platform post ID, or Telegram delivery confirmation. A green job or closed UI dialog alone is insufficient.
- **Idempotency:** check for an existing public post before creating one; persist post IDs/permalinks and retry writes safely.
- **Secrets:** never log or commit tokens, OAuth JSON, browser storage state, service-account JSON or API keys. Document secret names only.
- **Legal accuracy:** ground legal claims in verified sources; never invent statute numbers, penalties, case numbers or dates.
- **Provider quotas:** no free-tier/provider should be described as guaranteed. On Gemini quota exhaustion, stop trying alternate Gemini model names in the same project and use a verified-source fallback.
- **Cleanup:** inspect callers/workflows before deleting files. Review exact Blogger post IDs and contents before deleting drafts.
- **Image debugging:** trace final post → image brief → provider/model → exact output file → provenance hash → QA result → uploaded asset. Do not diagnose from prompt text alone.

## Secret names referenced by workflows (names only)

Depending on workflow: `BLOGGER_OAUTH_JSON`, `BLOGGER_UI_STORAGE_STATE_B64`, `BLOGGER_BLOG_ID`, `BLOGGER_URL`, `BLOGGER_ENABLED`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CREDENTIALS`, `GOOGLE_SHEET_URL`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_RANGE`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, Cloudflare account/token secrets, and platform-specific Meta/LinkedIn tokens. Do not add secret values to either handoff file.

## Recent implementation commits

- `74634632f17129b316271bd5bd694a8e5eee6941` — cap Reel whiteboard output duration and stop looped overlay inputs.
- `1e53aa926239973288a581ce0daca491684323e4` — allow Blogger demand article fallback without Gemini key and stop retrying shared 429 quota.
- `e551664c4ad280ddc7dc7994714689d9e076847f` — image provider/prompt/file provenance.
- `7b313780fd7796b09ea9d6c74f74baf0559ddd64` — hard QA guidance against anachronistic imagery and record QA outcome.
- `6ac2e921a85b9c1a925752f6f1748d6374c49498` — regression test for contemporary visual QA.
- `c90a33228237aedd704aaf9d9d11180b62b538bd` — regression test for image provenance sidecar.
- `d1b84071fa1c21689f641b2828e343f5c8afa7fa` — prevent explicitly rejected legal images from social publishing.

## Current acceptance checklist

- [ ] Blogger REST OAuth succeeds after secure re-authorization; secret updated.
- [x] At least one new Blogger demand article verified by public permalink (URL above).
- [ ] Blogger retry reuses exact existing public post and does not duplicate.
- [ ] Row-23 Reel renders under the Actions time budget, includes narration + spoken slogan + logo/end card, and Telegram delivery is confirmed.
- [ ] A current legal-topic image is inspected from the exact published asset; no irrelevant period-style imagery.
- [ ] Provenance sidecar records provider/model, prompt hash, final image hash and QA outcome.
- [ ] Quality Check passes for the final commit.
- [ ] Daily schedule acceptance: one slot/day, deterministic variable Cairo time 10:00–22:00, no parity filter.

## Latest evidence links

- Verified new Blogger demand article run: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054744408
- Failed row-23 Reel before duration-cap fix: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054152090
- Quality check after 720p/15fps Reel optimization: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38055120688

**Do not describe this handoff as a fully resolved project.** Blogger publishing has a verified successful path through the saved UI session, but REST OAuth needs owner action. Reel duration-cap and image-provenance/QA changes require post-commit workflow verification.
