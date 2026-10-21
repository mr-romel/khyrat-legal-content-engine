# Khyrat Legal Content Engine — Detailed Project Handbook and Handoff

**Repository:** https://github.com/mr-romel/khyrat-legal-content-engine  
**Production branch:** `main`  
**Documentation updated:** 2026-10-21 (Africa/Cairo)  
**Purpose:** End-to-end Egyptian legal content operations: legal-source research, editorial planning, platform-specific drafting, image generation and inspection, scheduled publishing, comments/engagement, Reels, Telegram approval, Blogger/SEO publishing, monitoring and marketplace experiments.

> This document distinguishes implemented code, test evidence, externally verified publication, known failures, owner actions and proposals. A commit is not proof of runtime success; a green GitHub Actions job is not proof that a social post or video became public.

## 1. Executive summary

The repository is a multi-workflow automation system, not one single publisher. It combines a core social publishing pipeline, Google Sheets as a planning/state surface, GitHub Actions as scheduler/worker orchestration, multiple AI and media providers, separate engagement workers, a Reel production/review process and Blogger workflows.

The most important current concerns are:
1. **Quality Check is failing on the latest observed main-branch commit.** The compile and application-import steps passed, as did the AI-router/output-contract tests. The image/Reel test group then failed because a regression test still expects two legacy whiteboard-overlay FFmpeg command strings. The production function was changed to remove the old whiteboard overlay layer entirely, so the test is stale relative to the current implementation. This blocks later checks in that workflow. Run: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39656731747
2. **Image QA is currently fail-open in code.** When the QA key is missing or the model call errors, the function returns PASS with scores of 100. This avoids a provider outage blocking the whole post, but it falsely represents an uninspected image as perfect and bypasses meaningful safety/quality review. This is a material quality issue and should be corrected to a transparent state such as QA_SKIPPED, with publication policy decided explicitly.
3. **Blogger OAuth REST access has previously failed with `invalid_grant`.** The owner must reauthorize the OAuth client and update `BLOGGER_OAUTH_JSON` if the error persists. Code cannot restore a revoked refresh token.
4. **The Reel duplicate-card fix is in code, but end-to-end verification is still required for the current build.** The desired architecture is one content video layer, one subtitle burn pass, and one brand end card; each spoken sentence must fit in one adaptive subtitle box.
5. **LinkedIn must remain a distinct B2B publication.** The image-repair path was changed so it no longer directly reuses the Facebook caption. Test the ordinary and image-repair paths and inspect the actual posted copy.
6. **External publication must be evidenced.** Require a public URL, platform post ID, or Telegram delivery receipt. Do not infer success from a green workflow, an updated spreadsheet status alone, or a closed confirmation dialog.

## 2. Project mission and operating principles

The engine exists to publish useful, accurate, professionally written Egyptian legal information and business-facing legal risk content, while minimizing manual work. It should not manufacture legal authority, publish a bad image just to satisfy a schedule, duplicate posts on retry, or hide failed QA behind a successful status.

### Editorial rules
- Write in natural, professional Egyptian Arabic appropriate to the platform and audience.
- Verify current Egyptian law, amendments, effective dates, statutory text and any cited official source before making specific claims.
- Never invent law/article numbers, penalties, deadlines, court cases, judicial principles, quotations, source names or dates.
- Do not use robotic filler, generic motivational wording, repetitive hooks, AI-production disclosures, internal planning labels, ellipses or unfinished endings.
- Avoid direct hard-sell CTAs such as booking a consultation or contacting the author. The content should be informative, practical and trustworthy.
- Reuse a subject only if the angle, purpose, examples, hook or practical guidance is materially different.
- Do not copy Facebook copy verbatim to LinkedIn. Platform copy may share verified legal facts, but each platform needs its own audience, structure, opening and practical angle.
- Never claim an article, image, Reel or post is published without the evidence appropriate to that destination.

### Scheduling rules
- One intended publishing slot per calendar date.
- Use Africa/Cairo time.
- Slot is deterministic for a date but variable across dates, between 10:00 and 22:00 inclusive.
- Do not introduce even/odd-date rules.
- Retries must be idempotent: if one platform succeeded while another failed, retry only the missing operation.
- Prioritize unpublished content and track both content identity and publication state.

### Security rules
- Never commit or print API keys, OAuth JSON, refresh tokens, cookies, browser storage state, service-account JSON or access tokens.
- Documentation may name secrets, never disclose values.
- Do not assume a platform permission exists because it would be useful. LinkedIn capability checks previously established `w_member_social`; do not assume `w_member_social_feed` is available.
- Treat provider quotas and free tiers as limited, not guaranteed.
- Review callers, workflow references and data dependencies before deleting files or cleaning up records.

## 3. Architecture and component responsibilities

### 3.1 Main content and publishing
- `src/run_main.py`: production entry/runner used by scheduled orchestration.
- `src/main.py`: primary social publication workflow; coordinates topic selection, drafting, editorial preparation, visuals, platform publication, comments/state and notifications.
- `src/content_system.py`, `src/content_system_runtime.py`: content strategy/runtime coordination and integration.
- `src/content_planner.py`: classifies and prepares planned topics/content.
- `src/social_content.py`: social-copy normalization, sanitization and hashtags.
- `src/content_style.py`, `src/content_style_v3.py`: writing/style rules.
- `src/post_bank.py`: published-post history and prior-content context.
- `src/topic_bank.py`, `src/topic_bank_500.py`, `src/topic_bank_expanded.py`: topic pools and topic diversity inputs.
- `src/daily_schedule.py`: one stable variable time slot per date.
- `src/monthly_recycler.py`, `src/recycler_rules.py`: monthly topic selection, canonical topic keys and angle rotation.
- `src/decision_engine.py`, `src/content_diversity.py`, `src/content_similarity.py`, `src/editorial_review.py`: candidate selection, similarity, diversity and editorial gates.
- `src/analytics.py`, `src/performance.py`, `src/production_monitor.py`: recording, measurement and operational summaries.

### 3.2 AI providers and content generation
- `src/gemini.py`, `src/gemini_runtime.py`, `src/gemini_chat.py`: generation/runtime integrations.
- `src/ai_router.py`: provider/model routing and quota/error fallback behavior.
- Content fallback must preserve legal source grounding. A fallback is not permission to invent legal details.
- When Gemini returns 429 quota exhaustion for a project, cycling through more model names in that same project is not a reliable recovery strategy. Stop repeated retries and choose an approved fallback or defer the task.

### 3.3 Legal research and search
- `src/legal_research.py`: legal-topic research/source collection.
- `src/legal_reference_registry.py`: legal-reference registry.
- `src/search_console_intelligence.py`, `src/search_geo.py`: search-demand and SEO/GEO-related intelligence/metadata.
- The system should retain the exact source URLs and source excerpts used for a legal claim so the final article can be audited later. A topic title or model-generated citation alone is not adequate evidence.

### 3.4 Image creation and inspection
- `src/image_generator.py`: image generation provider integration, post-derived visual brief, output asset and brand overlay.
- `src/image_qa.py`: final-image review/decision.
- `src/free_media.py`: media fallback/search.
- Keep the image provenance sidecar next to the final asset. It should identify provider/model, exact prompt, prompt hash, final image hash, and QA state/result.
- Trace image problems through the actual chain: published post → post text → visual brief → provider/model → exact output file → provenance → final QA → uploaded asset. Do not diagnose only from the prompt.
- Ordinary modern legal topics should use credible contemporary environments; do not inject Pharaonic/ancient styling unless the topic itself is about history or heritage.
- The prompt and QA policy currently prohibit women and girls in generated images. Treat that as an explicit project policy constraint, not a universal rule of legal imagery; it should be revisited only with the owner's direction.
- **Current concern:** the latest `src/image_qa.py` returns a synthetic PASS and scores of 100 if the QA key is missing or the vision request fails. This conflates “not checked” with “passed”. It should be replaced by explicit states such as PASS, REGENERATE, QA_SKIPPED and QA_ERROR, with a policy that can permit text-only publication while withholding an unverified image.

### 3.5 Reel and video
- `src/reel_pipeline.py`: Reel narration, scene/video assembly, brand card, subtitle integration, final validation and Telegram review handoff.
- `src/reel_subtitles.py`: timed Arabic sentence subtitle rendering; wraps the full sentence into one adaptive box and reduces font size as necessary.
- `src/reel_publishers.py`: destination publishing helpers.
- `src/video_layer.py`, `src/video_module/`: modular video planning, TTS, scenes, rendering and queue logic.
- `src/telegram_publication.py`, `src/telegram_bot.py`, `src/telegram_control.py`: delivery, review and approval/rejection controls.
- The intended output is vertical 9:16, correctly branded, with one subtitle box at a time. Every spoken sentence must be fully visible; no clipped lines, missing words, duplicate subtitle/card boxes or off-frame text.
- Subtitle timing should come from the actual narration segment data. Do not infer timing by guessing sentence durations if real timestamps are available.
- Bound render durations. Any FFmpeg still-image loop or overlay must have a hard duration/shortest-stream condition so it cannot create a video longer than the source audio/content.
- The Reel must be tested as a rendered MP4, not only through source-code assertions. Check dimensions, duration, audio, subtitle placement, one-box behavior, end card and Telegram receipt.
- For YouTube Shorts, if enabled, use the corresponding post text as the description and store/verify the actual video URL or ID.

### 3.6 Platform publishing and engagement
- `src/facebook_publisher.py`: Facebook publishing.
- `src/linkedin_publisher.py`: LinkedIn publishing and image upload operations.
- `src/facebook_engagement_worker.py`, `src/facebook_private_reply_worker.py`: Facebook comments/replies/engagement.
- `src/linkedin_engagement.py`, `src/linkedin_engagement_worker.py`, `src/linkedin_comment_engine.py`: LinkedIn engagement.
- `src/comment_engine.py`, `src/engagement_strategy.py`: contextual comment generation and strategy.
- Engagement is a separate concern from core post creation. A failed optional comment or reaction must not undo a post that was already published successfully.
- Intended comment volume: 3–7 distinct, contextual comments per post/platform, varying the number between posts. Where configured, a worker publishes at most one pending comment per run and records progress. Retries must not repeat already published comments.
- Use only the permissions and API operations actually granted. If a reaction/comment is unsupported, log that specific action as unavailable without falsely marking the core publication failed.

### 3.7 Blogger and SEO publishing
- `src/blogger_worker.py`: planned-content publishing.
- `src/blogger_demand_worker.py`: search-demand research and additional article workflow.
- `src/blogger_publisher.py`: Blogger REST/OAuth publishing and article HTML/labels.
- `src/blogger_ui_publisher.py`: Playwright UI fallback and publication/permalink verification.
- `src/blogger_editor.py`, `src/blogger_seo_worker.py`, `src/blogger_intelligence.py`, `src/blogger_identity_worker.py`, `src/blogger_pages.py`, `src/blogger_pages_ui_worker.py`, `src/blogger_site_setup.py`: SEO, identity, pages and site maintenance.
- Keep Blogger combined labels below the platform's length limit; regression tests cover label normalization.
- On retries, locate an existing exact-title/permalink article and reuse/update it instead of creating a duplicate.
- Do not bulk-delete drafts. Review exact IDs, titles, body and state first.
- Blogger UI success requires evidence that the exact article is Published and a public permalink can be retrieved. A closed modal is not proof.
- Verified article from prior run: https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_314.html — “كيفية التعامل مع الابتزاز الإلكتروني في مصر: الأدلة والخطوات القانونية التي يجب مراجعتها”.
- **Known external blocker:** REST OAuth previously returned `invalid_grant`. If still present, the account owner must reauthorize with the correct Blogger scope and securely replace `BLOGGER_OAUTH_JSON`. The saved Playwright session was a fallback, not a repair to the REST refresh token.

### 3.8 State, configuration and supporting workflows
- `src/config.py`: configuration and environment/secret loading.
- `src/sheets.py`: Google Sheets access/state updates.
- `src/token_manager.py`: token lifecycle helpers.
- `src/utils.py`: shared helpers, including Cairo time/date behavior.
- `src/marketplace/`, `src/marketplace.py`, `src/marketplace_mvp.py`, `src/marketplace_daily.py`: marketplace/opportunity workflows.
- Google Sheets should be treated as an operational state surface, but platform post IDs/permalinks and idempotency keys should be persisted explicitly. Spreadsheet status alone does not establish that the destination platform accepted the post.

## 4. Workflow inventory

The following workflows have been identified in the repository:
- `.github/workflows/publish-scheduled.yml`: scheduled production publishing; Reel handoff must use a real source row/artifact.
- `.github/workflows/quality-check.yml`: compile/import checks, targeted regression tests, architecture checks and full offline test suite.
- `.github/workflows/blogger-publisher.yml`: planned Blogger content.
- `.github/workflows/blogger-demand-daily.yml`: search-demand article publishing.
- `.github/workflows/blogger-oauth-check.yml`: Blogger OAuth health.
- `.github/workflows/blogger-intelligence.yml`, `blogger-pages.yml`: Blogger intelligence and site pages.
- `.github/workflows/reel-now.yml`: explicit retry for a locked Reel row and Telegram review.
- `.github/workflows/reel-daily-generator.yml`, `reel-production.yml`, `reel-publish-approved.yml`: daily generation, production and approved publishing.
- `.github/workflows/facebook-engagement-worker.yml`, `.github/workflows/linkedin-engagement-worker.yml`: independent engagement workers.
- Additional workflows cover token health, content intelligence, SEO/GEO, Telegram control, video pilots/layers, deployments and marketplace tasks. Inspect the actual YAML before changing any schedule or dispatch behavior.

## 5. Implemented changes and available evidence

### 5.1 Reel duration and duplicate subtitle/card layer
- Earlier Reel duration fixes added explicit output caps to main and emergency render paths and a regression test. A prior run reported row 23 rendered at 69.8 seconds and delivered to Telegram: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38055595685
- On 2026-10-21, the Reel path was changed to remove the extra whiteboard/card layer that could create a second caption box. `src/reel_subtitles.py` uses an adaptive single subtitle box per timed sentence.
- Current verification gap: the latest Quality Check fails because `tests/test_reel_overlay_duration_cap.py` still asserts two exact legacy FFmpeg command fragments that no longer appear after the overlay architecture was removed. This is likely a stale test, but the test must be updated to assert the current intended design and then the workflow rerun. Do not simply delete the test.
- The exact MP4 from the latest source still needs inspection for subtitle layout, full text, audio sync, final duration and branding.

### 5.2 Image prompt/provenance and QA
- `src/image_generator.py` was changed to pass a post-derived scene description directly and avoid an arbitrary `negative_prompt`.
- Image provenance was added in earlier commits, including provider/model, prompt/hash and final-image hash.
- The current QA behavior is advisory/fail-open, but it incorrectly reports PASS/100 on missing key or API exception. Fixing this is a high-priority improvement: preserve publication continuity via text-only fallback, not by falsely certifying an uninspected image.
- Inspect a real generated output and sidecar before declaring that the imagery issue is solved.

### 5.3 LinkedIn B2B copy
- Commit `606223916b2b2900c49c7805b80694679dbac8ed` changes the image-repair/republication path to prepare a LinkedIn-specific editorial version instead of passing the same Facebook text to both platforms.
- LinkedIn target: professional B2B legal-business writing for owners, management, HR, legal, compliance and operations; roughly 350–600 Arabic words when the subject supports it, with a depth gate and a 2,900-character safe cap. Explain business impact, risks, documents, responsibility and decision points.
- Do not address the audience directly as “أنت/إنت/عندك”; no sales pitch; different opening/structure/examples from Facebook.
- Verification needed: unit test for the normal path and image-repair path, including a generation failure fallback; inspect actual posted text and confirm platform post ID.

### 5.4 Blogger fallback and labels
- A demand article was verified by its public permalink above.
- Gemini 429 fallback was changed to stop cycling through model names on shared project quota exhaustion and use a verified-source fallback.
- Blogger label normalization and related tests were added to avoid overlong labels.
- OAuth REST access still needs owner-side repair if `invalid_grant` persists; do not represent the UI fallback as a permanent token fix.

### 5.5 Engagement workers
- Facebook and LinkedIn engagement workers have recently completed successfully in GitHub Actions, including runs at https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39657155344 and https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39657150023.
- These run statuses prove the worker process completed; they do not independently prove every intended comment or reaction appeared on the social platform. Check action-level logs, platform IDs and queue state.

## 6. Current known problems, root causes and remediation

### P0 — Quality Check blocks downstream tests
**Evidence:** latest observed run 39656731747 failed at `test_both_whiteboard_overlay_paths_are_duration_bounded`. Compile and import checks passed; the failure occurs in the targeted Reel/image test group, and subsequent test groups were skipped.  
**Likely cause:** the test asserts the old implementation's exact string twice, while current code deliberately uses `styled = base` and concatenates the base video with the end card, then burns subtitles separately.  
**Remediation:** rewrite the regression test around current behavior: assert the redundant overlay layer is absent, the content base and end card are assembled once, the subtitle burn is called once in the final path, and final duration validation remains present. Then run the focused tests and full Quality Check. Do not change production code solely to satisfy an obsolete string assertion.

### P0 — Image QA reports success when no inspection happened
**Evidence:** `qa_image()` returns decision PASS and scores 100 when no key is configured or the vision request throws.  
**Root cause:** a fail-open policy was implemented to avoid blocking text publishing during provider outages, but it encodes an operational bypass as a successful quality score.  
**Remediation:** return explicit QA states (PASS / REGENERATE / QA_SKIPPED / QA_ERROR); never fabricate scores. Allow the post to publish as text-only if policy allows, but do not attach an unverified image. Hard checks such as readable image, dimensions and file integrity should remain local and mandatory. Add tests for missing key, API exception, malformed JSON, irrelevant image, generated text, and explicit reject.

### P0 — Blogger OAuth token
**Evidence:** previous REST refresh failed with `invalid_grant`.  
**Root cause:** expired/revoked refresh token or OAuth app/account configuration; not repairable by changing application retry logic.  
**Remediation:** account owner checks consent-screen mode and authorized scopes, reauthorizes, updates `BLOGGER_OAUTH_JSON` in GitHub Secrets, then runs a safe OAuth health check. Never paste the JSON in chat or repository.

### P1 — Reel output needs end-to-end validation
**Evidence:** prior row 23 delivery succeeded at 69.8 seconds; the current architecture changed subtitle/card composition and the latest regression test is stale.  
**Risk:** a passing unit test alone cannot prove the subtitle box contains all spoken text or that the latest MP4 was actually delivered.  
**Remediation:** run the actual production Reel path on a known row; download/inspect the resulting MP4; check 9:16 dimensions, 15 fps if required, audio length, end card, one subtitle box, no clipping, no text outside the frame; confirm Telegram message ID and review status. Confirm Shorts URL/video ID if Shorts publication is enabled.

### P1 — LinkedIn content distinctness not yet proven end-to-end
**Evidence:** image-repair path has a code change, but tests and real post evidence are not yet established.  
**Risk:** a normal path can be correct while repair/retry uses a shared raw caption, or retries can duplicate a successful post.  
**Remediation:** test both paths; compare normalized text and reject near-identical cross-platform captions; persist per-platform success independently; verify the LinkedIn post ID/permalink.

### P1 — Idempotency and partial failures
**Risk:** a workflow can publish to one destination, fail on another, then duplicate the first post during retry.  
**Remediation:** maintain an idempotency key per content item/platform; persist remote post ID/permalink immediately after success; on retry, query stored state and only retry failed destinations. Add tests for partial success and retry.

### P1 — Evidence and observability are spread across logs and Sheets
**Risk:** a workflow can appear successful while the external action failed, or logs may not connect a row to a remote artifact.  
**Remediation:** standardize structured events: run ID, content ID/row, platform, action, status, remote ID/URL, retry count, error class, QA status and timestamp. Redact secrets and personal data. Create a single daily report that separates code-run success from external publication proof.

### P2 — Content originality and legal traceability
**Risk:** topic uniqueness checks can still miss semantic duplicates, and legal claims may lack a durable link between claim and official source.  
**Remediation:** persist normalized topic key, angle, source URLs, source retrieval date and final copy fingerprint. Use semantic similarity as a warning/review signal, not as the sole legal accuracy check. Require citations/source evidence for specific statutory claims.

### P2 — Provider quota and fallback policy
**Risk:** retries consume time without recovering from project-level quota exhaustion; generic fallbacks can reduce quality.  
**Remediation:** classify errors into quota, auth, transient network, invalid response and hard failure. Apply bounded retry with exponential backoff only to transient failures; use verified-source fallback for quota errors; stop on authentication errors until credentials are fixed.

## 7. Proposed improvement plan

### Phase A — Stabilize the build and truthfulness of status
1. Fix the stale Reel regression test to match the new single-layer architecture.
2. Change image QA status semantics so skipped/error is never reported as PASS.
3. Run all offline tests and require Quality Check green before making further production claims.
4. Add a release checklist for actual external evidence: post URL/ID, Telegram message ID, or Blogger public permalink.

### Phase B — Harden publication correctness
1. Add per-platform idempotency and partial-success recovery tests.
2. Verify LinkedIn distinct-copy requirements on every publishing path, including image repair.
3. Verify Blogger exact-title deduplication and UI/REST success reconciliation.
4. Ensure failed optional engagement never rolls back successful publication.

### Phase C — Improve asset quality
1. Add a local image integrity gate (file readable, expected aspect ratio, non-empty, dimensions).
2. Use QA status states and text-only fallback when visual QA is unavailable.
3. Add an automated subtitle timing/overflow test and a rendered-MP4 acceptance check.
4. Keep provenance for every final image and video; associate the asset hash with the content row.

### Phase D — Make monitoring actionable
1. Emit structured machine-readable status records for each platform action.
2. Generate a daily summary with planned slot, attempted items, published IDs/URLs, failed actions and owner action needed.
3. Alert only on actionable failures and avoid repeatedly retrying permanent errors.
4. Track content quality and outcomes: unique topic/angle, image QA status, post reach/engagement when available, and duplicate incidents.

## 8. Acceptance criteria

### Publishing and schedule
- [ ] Exactly one intended slot per calendar day, Cairo time, 10:00–22:00 inclusive.
- [ ] No even/odd-day filter.
- [ ] A successful post has a remote ID or public URL recorded.
- [ ] A retry does not duplicate an already successful destination.
- [ ] Partial failures resume only missing actions.

### Content and legal accuracy
- [ ] Specific legal claims have verifiable sources and current effective dates.
- [ ] No invented statutes, penalties, deadlines, citations or quotations.
- [ ] Topic/angle is not a near-duplicate of recent published content.
- [ ] Facebook and LinkedIn captions are platform-specific.
- [ ] LinkedIn reads as B2B professional copy, not Facebook-style conversational copy.

### Images
- [ ] Final file is readable and has correct dimensions/aspect ratio.
- [ ] Visual depicts the actual legal topic and is contemporary unless history is the topic.
- [ ] QA status accurately says PASS, REGENERATE, SKIPPED or ERROR.
- [ ] A skipped/error QA image is not falsely labeled as inspected.
- [ ] Provenance sidecar stores provider/model, prompt/hash, final image hash and QA result.

### Reels and Shorts
- [ ] Actual delivered MP4 is vertical and within configured duration limits.
- [ ] Only one subtitle box appears at a time.
- [ ] Every spoken sentence is completely visible, wrapped and in-frame.
- [ ] No duplicate caption layer, clipping, broken Arabic shaping or audio desynchronization.
- [ ] Brand end card is present exactly once.
- [ ] Telegram delivery is evidenced by a message ID/receipt.
- [ ] If Shorts is enabled, a YouTube video ID/URL is recorded and description matches the post text.

### Blogger and operations
- [ ] OAuth health check succeeds after owner reauthorization.
- [ ] Existing published articles are reused on retries.
- [ ] New article has a public permalink and verified Published state.
- [ ] Logs redact secrets and include actionable error categories.
- [ ] Full offline Quality Check passes.

## 9. Secret names (names only)

Depending on the enabled workflow, relevant secret/config names include:
- `BLOGGER_OAUTH_JSON`, `BLOGGER_UI_STORAGE_STATE_B64`, `BLOGGER_BLOG_ID`, `BLOGGER_URL`, `BLOGGER_ENABLED`
- `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CREDENTIALS`, `GOOGLE_SHEET_URL`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_RANGE`
- `GEMINI_API_KEY`, Cloudflare account/token secrets, Telegram bot/chat secrets, and platform-specific Meta/LinkedIn token secrets.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

Never add secret values to this file, `.context`, source code, issue comments or logs.

## 10. Evidence links and current status

- Latest observed Quality Check failure: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39656731747
- Another failed Quality Check on prior adjacent commit: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39656723448
- Recent successful LinkedIn engagement worker run: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39657155344
- Recent successful Facebook engagement worker run: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/39657150023
- Previously verified Blogger article: https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_314.html
- Previously confirmed Reel row 23 Telegram delivery (69.8 seconds): https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38055595685
- LinkedIn image-repair copy change: `606223916b2b2900c49c7805b80694679dbac8ed`
- Reel single-box/card-layer change: `1fa5226d0588c5aa45910ec63d811e38d0a100e1`

**Do not mark the whole project “fixed” until the current Quality Check passes, image QA status is truthful, the actual Reel is inspected, Blogger OAuth is repaired where needed, and external publication evidence is recorded.**
