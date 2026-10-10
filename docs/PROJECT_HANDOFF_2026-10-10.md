# Khyrat Legal Content Engine — Project Handoff (2026-10-10)

## Purpose and scope

Repository: https://github.com/mr-romel/khyrat-legal-content-engine
Default branch: `main`

This document is a handoff snapshot for a second engineer/AI reviewer. It distinguishes confirmed observations from hypotheses. It intentionally contains no credentials, tokens, cookie values, private keys, or secret payloads.

## Executive summary

The project is a multi-workflow legal-content automation system. It generates and publishes Egyptian legal content to social platforms, runs engagement workers, creates short-form reels with Telegram review/delivery, and publishes SEO/search-demand articles to Blogger. It also contains a marketplace/opportunity dashboard subsystem.

The immediate production issues are not resolved as of this snapshot:

1. **Blogger publication is not verified.** Recent runs fail because the Blogger REST API OAuth refresh returns `invalid_grant: Token has been expired or revoked`. The UI fallback fills a title and reports a publish confirmation dialog disappearing, but cannot prove a public permalink. The dashboard showed several `(Untitled)` drafts and repeated title rows. Do not treat a successful workflow step or a closed dialog as proof of public publication.
2. **Gemini quota is exhausted.** The search-demand article worker got HTTP 429 `RESOURCE_EXHAUSTED`; a source-grounded fallback exists, but publication still failed at verification/authentication.
3. **Blogger public-page verification is brittle.** The HTML search fallback received Google 429/rate-limit interstitial responses. Verification should use Blogger REST API when authorized, Blogger's feed/Atom endpoints where publicly accessible, or the authenticated dashboard's post ID/permalink—not Google search HTML as the primary source.
4. **Reel row 23 failed before Telegram delivery.** The error was `REEL_STAGE fallback_branding_failed` while FFmpeg processed a whiteboard overlay chain with four card images and repeated hand-marker image inputs. A simplified four-card overlay and one-card branded fallback were committed, but the newest scheduled run was still in progress at snapshot time; there is no verified successful delivery yet.
5. **Images still appear pharaonic despite an explicit anti-pharaonic prompt.** `src/image_generator.py` already prohibits pyramids, temples, hieroglyphs, pharaohs, papyrus and other ancient-Egypt imagery unless the article is explicitly about antiquities. The remaining cause is not yet proven. Likely areas to inspect are how `visual_description` is derived, which generator/provider actually served the final image, whether QA checks the final output and blocks pharaonic imagery, and whether cached/pre-existing assets can bypass regeneration.
6. **Workflow success and business success are conflated in places.** Validate external results (public permalink, Telegram delivery message/video, social post ID) before recording a job as fully successful.

## Recent run evidence

Repository Actions page: https://github.com/mr-romel/khyrat-legal-content-engine/actions

- Scheduled workflow run `38046936167`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046936167
  - Snapshot status: `in_progress`.
  - Core Social Publisher: succeeded.
  - Publishing Artifact: succeeded.
  - Reel Generator + Telegram Review: in progress at dependency installation.
  - Blogger Publisher: in progress at dependency installation.
  - Facebook/LinkedIn engagement jobs were also in progress.
  - This run must be checked again before drawing conclusions.
- Blogger Daily Search Demand Article run `38046557377`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046557377 — failed.
- Quality Check run `38046557382`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046557382 — succeeded for the code snapshot that run tested. This does not prove Blogger publishing works.
- Blogger Daily Search Demand Article run `38046292110`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046292110 — failed.
- Blogger SEO GEO Publisher run `38046030551`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046030551 — workflow reported success, but its logs showed it reused/checked a public title and does not prove a new article was published during that run.
- Prior scheduled run `38043459191`: https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38043459191
  - Core Social Publisher, Facebook Engagement, Facebook Comment Replies, LinkedIn Engagement, Publishing Artifact, Blogger SEO Search Description, Blogger Site Identity + Pages succeeded.
  - Reel Generator + Telegram Review failed.
  - Blogger Publisher failed.
  - Blogger Brand Identity + Description failed.
- Reel row 23 Telegram error (user-provided): `fallback_branding_failed` while FFmpeg rendered `generated/reels/row_23/motion/whiteboard_base.mp4` plus four `whiteboard_card_*.png` overlays and repeated `whiteboard_hand_marker.png` inputs. This was a pre-delivery failure; no Telegram delivery occurred for that attempt.

## Confirmed Blogger diagnostics from run logs

In the 2026-10-10 search-demand run:
- Google Gemini API returned `429 RESOURCE_EXHAUSTED` and reported the free-tier daily request quota was exceeded, with a retry delay of about 13 hours at the time of the run.
- Blogger REST API token refresh failed with `invalid_grant: Token has been expired or revoked.`
- The UI fallback logged that the title field was filled and verified for a title about handling electronic blackmail in Egypt.
- It logged that the publish confirmation dialog was no longer visible.
- The dashboard body excerpt showed multiple `(Untitled)` drafts and repeated rows for another article.
- It did not find an exact matching published row/permalink.
- The public HTML lookup received HTTP 429 from a Google rate-limit interstitial.
- The run exited with code 1. Keyword-map persistence logged success afterward, but that does not change the failed publication result.

## Current architecture map

### GitHub Actions workflows

- `.github/workflows/publish-scheduled.yml`: primary scheduled production publishing.
- `.github/workflows/quality-check.yml`: architecture/quality tests.
- `.github/workflows/blogger-publisher.yml`: Blogger publisher for existing content.
- `.github/workflows/blogger-demand-daily.yml`: daily search-demand article.
- `.github/workflows/blogger-intelligence.yml`: Blogger content intelligence.
- `.github/workflows/blogger-oauth-check.yml`: OAuth health/diagnostic path.
- `.github/workflows/blogger-pages.yml`: Blogger pages.
- `.github/workflows/reel-now.yml`, `reel-daily-generator.yml`, `reel-production.yml`, `reel-publish-approved.yml`: reel generation/production/review paths.
- `.github/workflows/facebook-engagement-worker.yml` and related Facebook reply/private-reply workflows: engagement/reply workers.
- `.github/workflows/linkedin-engagement-worker.yml` and CI/dry-run/token diagnostic workflows: LinkedIn engagement.
- Other workflows cover content intelligence, SEO/GEO, token health, Telegram controls, video pilot/layers, deployment and marketplace discovery/operations. Review the actual workflow YAML before changing triggers; marker files can intentionally trigger jobs.

### Core source modules

- Scheduling/content plan: `src/daily_schedule.py`, `src/recycler_rules.py`, `src/monthly_recycler.py`, `src/post_bank.py`, `src/topic_bank.py`, `src/topic_bank_500.py`, `src/topic_bank_expanded.py`.
- Main content/publishing: `src/run_main.py`, `src/main.py`, `src/content_system.py`, `src/content_system_runtime.py`, `src/content_planner.py`, `src/social_content.py`, `src/content_style.py`, `src/content_style_v3.py`.
- Content intelligence/quality: `src/content_intelligence.py`, `src/content_intelligence_engine.py`, `src/content_diversity.py`, `src/content_similarity.py`, `src/editorial_review.py`, `src/decision_engine.py`, `src/analytics.py`, `src/performance.py`.
- Images: `src/image_generator.py`, `src/image_qa.py`, `src/free_media.py`.
- Legal sources: `src/legal_research.py`, `src/legal_reference_registry.py`, `src/search_console_intelligence.py`, `src/search_geo.py`.
- Blogger: `src/blogger_worker.py`, `src/blogger_demand_worker.py`, `src/blogger_publisher.py`, `src/blogger_ui_publisher.py`, `src/blogger_editor.py`, `src/blogger_seo_worker.py`, `src/blogger_intelligence.py`, `src/blogger_identity_worker.py`, `src/blogger_pages.py`, `src/blogger_pages_ui_worker.py`, `src/blogger_site_setup.py`.
- Reels/video: `src/reel_pipeline.py`, `src/reel_publishers.py`, `src/video_layer.py`, `src/video_module/` (brand, captions, script, scene planning, rendering, queue, reservation, validation, TTS and whiteboard components).
- Social publishing/engagement: `src/facebook_publisher.py`, `src/facebook_engagement_worker.py`, `src/facebook_private_reply_worker.py`, `src/linkedin_publisher.py`, `src/linkedin_engagement_worker.py`, `src/linkedin_comment_engine.py`, `src/engagement_strategy.py`.
- Shared integrations: `src/config.py`, `src/sheets.py`, `src/gemini.py`, `src/gemini_runtime.py`, `src/gemini_resilience.py`, `src/token_manager.py`, `src/telegram_bot.py`, `src/telegram_publication.py`, `src/telegram_control.py`, `src/utils.py`.
- Marketplace subsystem: `src/marketplace.py`, `src/marketplace_daily.py`, `src/marketplace_mvp.py`, `src/marketplace/`, `api/index.py`, `android/`, `marketplace_data/`, and related deployment documentation.
- Tests include architecture acceptance, content system/intelligence, Blogger, image QA, legal research, LinkedIn, Facebook engagement and marketplace tests.

### Supporting documentation/data

- `docs/BLOGGER_ENGINE.md`, `docs/BLOGGER_SETUP.md`, `docs/SEO_GEO_IMPLEMENTATION.md`, `docs/LINKEDIN_ENGAGEMENT_WORKER.md`, marketplace rollout/deployment docs, `AUTOMATION_V2_SETUP.md`, `CHANGES.md`.
- `data/blogger_keyword_map.json`: search-demand keyword history/state.
- `assets/reference/`: reference photos used by image identity workflows. Treat as private project assets; do not publish or bundle into public handoff files unless explicitly approved.
- `.env.example`: environment variable names/examples only. Never copy real GitHub secrets or OAuth/storage-state payloads into handoff documents.

## Open problems and acceptance criteria

### P0 — Blogger OAuth and reliable publication
- Reconnect/refresh Blogger OAuth outside the code, then update the repository secret `BLOGGER_OAUTH_JSON` using the valid token payload. Do not paste credentials into chat or commit them.
- Verify that `BLOGGER_UI_STORAGE_STATE_B64` is current if UI fallback remains supported; it is a session fallback, not a substitute for fixing OAuth.
- Prefer Blogger REST API publication and retrieve the returned post ID/permalink. If API auth is unavailable, do not silently claim success.
- Fix UI fallback to verify title, body persistence/autosave, publish confirmation, published dashboard row, and the canonical public URL. A modal disappearing is insufficient.
- Add duplicate prevention by canonical post ID/title/content fingerprint before creating a new post; clean up the current `(Untitled)` drafts and duplicates manually or through a safe, reviewed cleanup routine. Never delete posts without checking IDs/content first.
- Replace Google search HTML as the primary permalink verifier. It is rate-limited and returned 429. Use authorized Blogger API, Blogger feed/Atom, or authenticated dashboard details.
- Acceptance: a new article's public permalink is captured, opened/verified, and recorded in logs/state; rerunning the same input does not create another post.

### P0 — Search-demand article generation under quota limits
- Gemini free-tier quota was exhausted. Decide whether to enable billing/raise quota or route to a separately configured provider. Never assume changing the model name avoids project-wide quota limits.
- Preserve the legal-source fallback, but require sufficient verified source material and citations in the article; do not generate legal rules/case numbers from memory.
- Acceptance: a demand article is produced from observed search suggestions plus verified legal sources, and then actually published and permalink-verified.

### P0 — Reel row 23 FFmpeg rendering and delivery
- Previous overlay graph had four cards and repeated marker images, large x-motion expressions, escaped commas, and expensive encoding. It failed in `fallback_branding_failed` before Telegram delivery.
- A simplified renderer/fallback was committed to reduce FFmpeg complexity, but this snapshot has no verified successful run after that change.
- Recheck current `reel-now.yml` run and logs. Validate FFmpeg syntax, output file existence, duration, audio, brand end card, logo, and slogan audio before Telegram upload.
- The renderer must not deliver unbranded output; however, it should fail with a concise diagnostic and preserve the intermediate artifacts for debugging rather than returning an opaque giant command.
- Acceptance: row 23 produces a playable, branded video with whiteboard cards, logo/brand end card and slogan audio; Telegram reports successful delivery and the run records the message/video reference.

### P1 — Pharaonic/irrelevant generated images
- Current `src/image_generator.py` already has a strong anti-pharaonic rule and a negative prompt. The continued symptom suggests a mismatch elsewhere in the actual image path.
- Trace a single affected row end to end: post text → generated `visual_description` → provider/model selection → exact output file and cache path → final image QA prompt/decision → image uploaded to the post.
- Log a short safe audit record: row ID, visual-description text, provider/model name, image SHA-256, QA decision/score/reasons, and final uploaded image URL; never log tokens.
- Make modern contemporary Egypt explicit in the positive prompt (e.g. present-day Egyptian workplace/home/police-report setting only if supported by the article) and hard-block pharaonic motifs in final QA unless the topic is antiquities.
- Ensure QA examines the exact final file that will be uploaded, not a different/pre-regeneration image. Reject/retry when ancient-Egypt imagery appears. Ensure cached images are rechecked against the current post.
- Acceptance: test a diverse batch of legal topics and confirm each image visually depicts the article's concrete legal scenario; no pyramids/temples/hieroglyphs unless the subject is explicitly ancient history.

### P1 — Scheduling and state consistency
- Required schedule contract: exactly one slot per calendar day, Cairo time, deterministic but variable time from 10:00 through 22:00 inclusive; no even/odd-day restriction.
- A previous even-day patch was removed. Commit referenced in prior context: `1c683cec1a01e206e432edcbf990ebfd29a76a9f`.
- Verify `src/daily_schedule.py`, `src/recycler_rules.py`, `src/monthly_recycler.py`, `src/content_system_runtime.py` and the acceptance tests before altering schedule behavior.
- Acceptance: exactly one slot per date, every day present, no duplicates, every time within the permitted range, variable times, Cairo timezone.

### P1 — Run status and publication truth
- A green workflow is not equivalent to a public post. Log external post IDs/permalinks/message IDs and separate statuses such as generated, submitted, platform-confirmed, publicly verified.
- Keep artifact persistence and keyword-map writes separate from publication success.
- Make retries idempotent; do not create duplicate posts if a previous attempt published but failed while writing state.

### P2 — Maintainability and project cleanup
- Repository has many independent workflows and multiple subsystems. Before deleting “unused” code, search all imports, workflow invocations, script entrypoints, and documentation references.
- Keep secret names in docs but never secret values.
- Add smoke tests for the exact Blogger and reel failure cases, plus a report-only diagnostics mode where possible.

## Suggested work order for the next engineer

1. Recheck run `38046936167` and all jobs; read failure logs after it completes.
2. Restore Blogger OAuth credentials through the GitHub Secrets UI or secure OAuth setup process; never share token JSON in a prompt.
3. Reproduce Blogger publication with one unique test title; capture the returned post ID and public permalink before updating state.
4. Fix UI publishing only after using logged DOM/dashboard evidence. Avoid more blind selector changes.
5. Resolve image-generation path and QA using one affected row and the exact final asset hash.
6. Verify the simplified reel renderer with a full end-to-end row-23 run, including Telegram delivery.
7. Run the quality/architecture tests and the relevant workflows after each isolated change.

## Secrets and privacy

Do not put values for `BLOGGER_OAUTH_JSON`, `BLOGGER_UI_STORAGE_STATE_B64`, Google/Gemini API keys, Cloudflare credentials, Meta tokens, LinkedIn tokens, Telegram bot tokens, service-account JSON, or any other secret in this document. The names may appear as references, but values must remain in GitHub Secrets or the appropriate secure secret manager.

## Evidence and uncertainty policy

- **Confirmed:** supported directly by the run logs summarized above or the checked source.
- **Hypothesis:** a likely cause to test, not a proven diagnosis.
- **Not verified:** no successful external outcome was observed.
- Update this file after a successful permalink-verified Blogger publication and a successful branded Reel Telegram delivery.


## Addendum — latest scheduled run evidence (checked 2026-10-10 14:04 Cairo)

The previously in-progress scheduled run `38046936167` advanced:
- Core Social Publisher: success.
- Blogger Publisher: success.
- Blogger SEO Search Description: success.
- Facebook engagement, Facebook comment replies and LinkedIn engagement: success.
- Reel Generator + Telegram Review: **failed**.
- Blogger Site Identity + Pages was still in progress at the last check.

Blogger Publisher's logs now provide a verified public feed permalink:
https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_595.html
The title is `ما الذي يجب مراجعته قبل اتخاذ أي إجراء قانوني؟`. The worker explicitly logged `Blogger duplicate prevention: reusing existing public post`; therefore this is a verified existing public post reused by the run, **not proof that a new demand article was created today**. Gemini quota remained exhausted, and the worker used the structured fallback before finding/reusing that public post. This is meaningful progress: at least one public Blogger permalink is now verified by the publisher's feed lookup, while the demand-article workflow and OAuth refresh issue remain separate blockers.

The same scheduled run's Reel job has a newer and more specific failure:
- Artifact download failed: `Artifact not found for name: reel-source-context`.
- The worker then recovered/locked row 23 and built a deterministic script fallback because Gemini returned 429 quota errors.
- Edge Egyptian Neural TTS succeeded and produced about 64.4 seconds of narration.
- Openverse returned zero assets.
- MoneyPrinterTurbo fallback could not find its cloned directory and switched to the FFmpeg fallback.
- The final blocking error was `Spoken brand slogan generation failed; refusing delivery`, because Gemini was unavailable for slogan generation. This occurred before Telegram delivery.
- Therefore, the latest run did **not** establish that the simplified whiteboard FFmpeg renderer itself still fails; the run failed earlier at missing artifact and then at slogan generation. Fix the missing `reel-source-context` artifact contract and make the branded end-card slogan use a deterministic pre-recorded/local fallback that does not depend on Gemini quota. Continue to refuse unbranded delivery.

Updated immediate priority:
1. Fix Reel artifact production/consumption so the consumer can gracefully regenerate context from the locked sheet row if the artifact is absent.
2. Store or generate the branded spoken slogan independently of Gemini (for example, a checked-in/non-secret audio asset or the already configured Edge Neural TTS path) and validate it before rendering.
3. Re-run row 23 end-to-end and verify Telegram delivery.
4. Continue Blogger demand-article OAuth and quota work; do not confuse the verified existing post permalink with a new demand article.


## Addendum — live verification after the previous snapshot (2026-10-10)

### Current run results

- Scheduled workflow `38046936167` is **completed / failure**: [open run](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046936167).
  - Core social publisher: success.
  - Blogger Publisher: success, but this run reused an already-public article through duplicate prevention; do not interpret it as a new demand article.
  - Blogger SEO Search Description and Blogger Site Identity + Pages: success.
  - Facebook/LinkedIn engagement and comment-reply jobs: success.
  - Reel Generator + Telegram Review: failure.
  - Blogger Brand Identity + Description: failure.
- Blogger Daily Search Demand Article `38046557377`: **failure** ([open run](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38046557377)).
- Quality Check `38047154627`: **success** ([open run](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38047154627)). This is code/test evidence only, not external publication evidence.

### Reel failure: exact root cause in the latest run

The latest scheduled Reel run did not reach the simplified FFmpeg card-overlay failure reported in the earlier Telegram alert. It failed later in the branding stage:
- Cross-workflow artifact download failed: `Artifact not found for name: reel-source-context`.
- Gemini quota returned HTTP 429 `RESOURCE_EXHAUSTED`.
- Main narration recovered successfully using Edge Egyptian TTS, duration about 64.4 seconds.
- Openverse returned zero assets.
- MoneyPrinterTurbo's expected cloned directory was missing, so the pipeline switched to its FFmpeg fallback.
- The final blocking exception was `Spoken brand slogan generation failed; refusing delivery`: Gemini was unavailable, and the fallback logged `edge-tts is not installed`.
- No Telegram delivery was confirmed.

**Recommended fix:** store a licensed, pre-recorded slogan MP3 as a stable project asset, or install and test `edge-tts` as a deterministic fallback. Do not require Gemini quota for a fixed brand slogan. Also make the Reel worker regenerate source context from the exact locked Sheet row or pass the producing workflow's explicit run ID/token; artifact names alone do not make artifacts available across different workflow runs.

### Blogger demand publishing: exact current blockers

The latest demand run confirms:
- Gemini free-tier quota is exhausted across the configured model attempts.
- Blogger REST API refresh fails with `invalid_grant: Token has been expired or revoked.`.
- The UI fallback fills/verifies the title field and observes the publish dialog disappear, but cannot find a matching published dashboard row/permalink.
- Google HTML search fallback receives a 429 rate-limit interstitial.
- Therefore, **no new demand article was verified as publicly published** by this run.

The primary fix is to re-authorize Blogger OAuth securely and update GitHub Secret `BLOGGER_OAUTH_JSON`. The hypothesis that the token expired because the consent screen is External + Testing and tokens expire after seven days must be confirmed in the actual Google Cloud Console; it is not proven by `invalid_grant` alone. Keep token payloads out of chat and the repository.

Use the Blogger REST API's returned post ID/permalink or Blogger feed/Atom verification where available. Do not use Google Search HTML as the primary verification path. A dialog closing is not publication success. Retry logic must be idempotent, and existing drafts/duplicates should be inspected by post ID and body before cleanup.

### Blogger brand identity workflow

The scheduled run's Blogger Brand Identity + Description job failed with:
`Blogger Layout: Add a Gadget control not found and public navigation is incomplete.`
The log says the header gadget was updated through a visual keyboard fallback, but the worker still could not verify the navigation state. Fix with DOM evidence and safe checks; avoid blind coordinate clicks or claiming success based only on partial changes.

### Evaluation of the proposed repair plan

1. **OAuth:** External + Testing can cause a seven-day refresh-token lifetime, but first verify the consent-screen publishing status. Securely re-authorize and update the secret. Blogger email publishing is only an optional alternative if configured; it is not automatically more reliable.
2. **Provider chain:** Groq, OpenRouter free models, and Cloudflare Workers AI are candidate providers, not a working fallback until access, quotas, terms, required secrets, adapters, and legal-source quality are tested. Do not promise permanently free capacity.
3. **Brand slogan:** a fixed checked-in MP3 is the most deterministic low-cost route if the asset is licensed and tested.
4. **Artifacts:** use durable committed context or an explicit cross-workflow run ID/token; do not assume artifact visibility across runs.
5. **Pharaonic images:** the current image QA already has a contemporary-Egypt rule. Trace the exact final image through brief, provider/model, cache, QA, and uploaded URL; prompt changes alone are not enough.
6. **Blogger verification:** public permalink plus post ID is a hard acceptance gate. Keep external-publication state separate from artifact persistence or a green workflow.

### Next actions, in order

1. Re-authorize Blogger OAuth and update `BLOGGER_OAUTH_JSON` without exposing credentials; publish one uniquely titled test article and capture its post ID and public URL.
2. Fix Blogger idempotency and permalink verification; do not create another draft if the same post already exists.
3. Add the stable spoken-slogan asset and fix the Reel source-context artifact contract; rerun row 23 and verify Telegram delivery.
4. Repair the Blogger Layout navigation worker using DOM evidence.
5. Audit the image provider/cache/final-asset path and add a hard QA rejection for ancient-Egypt motifs in modern legal posts.
6. Add alternate AI providers only after tests for access, quotas, timeouts, source-grounded legal accuracy, and provider provenance.


## Remediation update — 2026-10-10

This section supersedes older snapshot statements above when they conflict with the changes and evidence below.

### Image prompt changes now committed
- `src/gemini.py`: the image-brief instructions now positively describe a single modern, post-specific scene. They no longer list named ancient/historical motifs as things to avoid.
- `src/image_generator.py`: the Cloudflare/Gemini image prompt is now centered on the supplied scene, present-day everyday objects and documentary composition. Explicit Egypt/Egyptian and named ancient-motif tokens were removed from both prompt and negative prompt.
- `src/image_qa.py`: the QA prompt checks whether the image depicts the concrete present-day action and setting, without repeating a list of historical motifs.
- `src/reel_pipeline.py`: stock-search terms and the Reel brief now describe the actual people/action/evidence in modern settings. Named historical-style terms were removed from the visual prompt/search descriptions.
- Regression test `tests/test_image_generator_prompt.py` was added and is now part of the image tests in `.github/workflows/quality-check.yml`. It captures the request body and asserts that the post-derived scene is present and the known trigger terms are absent.

### Reel root cause and code fix
The failed scheduled run `38050498346` confirmed:
- Main narration succeeded.
- Gemini quota was exhausted with HTTP 429.
- The fixed brand slogan fallback failed with `edge-tts is not installed`, even though the package is part of the Reel requirements. The function used `shutil.which("edge-tts")`; the scheduled workflow invokes the script through a virtualenv Python, so the executable was not necessarily on global PATH.
- The renderer fell back to FFmpeg because MoneyPrinterTurbo was unavailable; Openverse returned zero assets.
- Telegram delivery was not reached.

Fixes committed:
- `generate_local_short_neural_tts` now invokes `sys.executable -m edge_tts`, checks the output file and validates its duration.
- The fixed slogan tries Edge Neural TTS first and calls Gemini only if Edge TTS fails, reducing avoidable Gemini quota use.
- `.github/workflows/publish-scheduled.yml` now exports whether the core publishing run created a locked Reel source file. The scheduled Reel job is skipped when no new source file exists, instead of downloading a nonexistent artifact and attempting to recover an older row. Explicit retries remain in `reel-now.yml`.

**Not yet verified:** a successful final MP4 after the new TTS path, correct logo/end-card/slogan, and actual Telegram delivery. A green syntax test alone is not sufficient.

### Blogger publication state and fixes
- `src/blogger_demand_worker.py` now allows REST API-only configuration to start without requiring a browser storage-state secret. The UI session is needed only as a fallback.
- It now checks the public Blogger feed for an exact existing title before publication and reuses that post rather than creating another duplicate.
- The primary Blogger publisher's job in run `38050498346` logged a verified public permalink and duplicate-prevention reuse:
  [Existing public article](https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_595.html)
  Title: **ما الذي يجب مراجعته قبل اتخاذ أي إجراء قانوني؟**
  This proves a public post exists. The run reused the existing article, so it does **not** prove a new article was created by that particular run.
- OAuth refresh still returned `invalid_grant: Token has been expired or revoked` in earlier demand-worker runs. This is not fixable in repository code: the account owner must check the Google Cloud OAuth consent screen status, re-authorize using the correct Blogger scope, and replace `BLOGGER_OAUTH_JSON` in GitHub Secrets. Do not share token JSON, cookies, or storage state in chat.
- Gemini 429 remains a provider quota issue. The cautious legal-source article fallback is in code, but the demand worker must be re-run and a genuinely new public permalink verified before calling it fixed.
- The Blogger Brand Identity/Layout job also failed because its expected “Add a Gadget” control was not found. This is a separate cosmetic/layout worker and should not be confused with article publication.

### Current remaining blockers
1. **Manual OAuth reauthorization:** update `BLOGGER_OAUTH_JSON` securely after changing/checking the consent-screen publishing status. Code cannot resurrect a revoked refresh token.
2. **Verify new demand article:** run `blogger-demand-daily.yml`; inspect its exact job logs; require a new public URL, not just a closed dialog or a reused old permalink.
3. **Verify Reel:** run the explicit row-23 retry only after quality check passes; require playable MP4, slogan audio, logo/end card, and Telegram delivery confirmation.
4. **Inspect real generated images:** compare the exact uploaded file and logged provider/prompt against the legal post. Prompt cleanup is committed but visual output has not yet been revalidated after the change.
5. **Do not delete Blogger drafts blindly:** inspect exact IDs and bodies before cleaning up “Untitled” drafts.

### Latest relevant Actions evidence
- Scheduled run with the confirmed slogan-path and prompt root causes: [38050498346](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38050498346)
- Quality run for the demand publisher guard/idempotency change: [38053820070](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38053820070) — succeeded for that commit.
- Final prompt/workflow regression quality run started by the latest changes: [38053898614](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38053898614) — was in progress at the time of this note. Re-check it after the final documentation/test commits.

### Acceptance gates
- Blogger: newly created article ID and canonical public permalink verified; retry is idempotent.
- Reel: MP4 playable and within duration cap, narration and spoken slogan present, logo/end card present, Telegram delivery confirmed.
- Images: prompt derived from the final post; no ancient/historical visual leakage for routine legal topics; inspect the exact final image asset.
- Scheduling: exactly one deterministic variable slot per day in Cairo time between 10:00 and 22:00; no even/odd-day restriction.
- Security: no secret values, OAuth JSON, access tokens, cookies, or browser storage-state payloads in repository/docs/logs.


## Additional production finding: Blogger label validation

The scheduled run [38054198942](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054198942) exposed a concrete blocker beyond OAuth: Blogger displayed **“The combined length of all the labels must be at most 200 characters.”** The UI flow then closed the confirmation dialog, but the exact title did not appear as a Published dashboard row and no public permalink was verified. The run failed correctly rather than reporting success.

Fix committed:
- Added shared `normalize_blogger_labels()` in `src/blogger_publisher.py`.
- All Blogger workers and the UI fallback now deduplicate labels, remove commas/newlines inside individual labels, limit each label to 40 characters, use at most 10 labels, and keep the joined label string at 180 characters (below Blogger's 200-character combined limit).
- Added `tests/test_blogger_labels.py` and wired it into the quality workflow.
- Quality run [38054573571](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054573571) succeeded with the Blogger label regression tests passing.

Follow-up runs:
- [Blogger SEO GEO Publisher 38054641111](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054641111) succeeded, but it reused the already-public article [“ما الذي يجب مراجعته قبل اتخاذ أي إجراء قانوني؟”](https://askmahmoudkhyrat.blogspot.com/2026/10/blog-post_595.html). It does **not** prove that a new article was created by that run.
- [Blogger Daily Search Demand Article 38054744408](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054744408) was triggered after the label fix; inspect its final logs for a newly created public permalink.
- [Reel Now row-23 retry 38054152090](https://github.com/mr-romel/khyrat-legal-content-engine/actions/runs/38054152090) was still in progress at the latest check. This run started before the unused `voicetut-tts`/OmniVoice setup was removed from `reel-now.yml`; future retries should install fewer unnecessary dependencies.
