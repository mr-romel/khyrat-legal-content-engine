# Khyrat Legal Content Engine — Facebook Quality Upgrade

This package upgrades the Facebook stage from a Pillow text-card to real AI-generated visuals using Gemini 3.1 Flash Image (Nano Banana 2), then publishes the image + post caption and adds a first comment. Auto-like is attempted as an optional action; if Meta rejects it, publication still succeeds and the reason is logged.

## Replace/add these files
- Replace `src/main.py`
- Replace `src/config.py`
- Replace `src/image_generator.py`
- Replace `src/facebook_publisher.py`
- Replace `.github/workflows/publish.yml`
- Replace `requirements.txt`

## Required GitHub Secret
`FACEBOOK_PAGE_ACCESS_TOKEN`

The Page ID is currently set to `464216073916915`.

## Visual behavior
- 4:5 Facebook feed image
- Real scene / editorial visual
- No explanatory text in image
- No title duplicated inside image
- Topic-specific visual concept
- Legal-brand palette, without generic scales unless relevant

## Engagement behavior
After publishing, the engine adds a first Page comment. It also attempts a programmatic like; this action is optional because Meta may restrict it depending on current API capabilities. The workflow does not fail just because an optional like is rejected.


## Final Image Preview / QA Gate

Before any Facebook or LinkedIn publication, the final rendered JPEG is inspected by a Gemini vision QA pass.

The gate checks:
- hard 4:5 output dimensions
- social-feed composition and safe crop
- unexpected AI-generated text, while allowing only the intentional bottom-right brand overlay
- direct relevance to the legal topic and image brief
- recurring-character consistency against the reference images

The reference images under `assets/reference/` remain the identity source. They are analyzed into a reference-derived identity profile that is inserted into the image-generation prompt, and the actual reference images are also supplied to the visual QA model for comparison.

If QA returns `REGENERATE`, the QA correction is appended to the visual brief and the image is generated again. Publication is blocked after the configured retry limit or on a hard QA error. A failed/recovered image is never published merely because the file already exists.

Google Sheets records `Image QA Status`, `Image QA Score`, `Image QA Issues`, and `Image QA Attempt`.


## Engagement Worker

Facebook and LinkedIn engagement is handled by `src/facebook_engagement_worker.py` and `src/linkedin_engagement_worker.py`, independently from the publisher.

For each published post:
- the worker attempts one post reaction on each available platform;
- it publishes a deterministic, post-specific queue of **3 to 7 comments** per platform;
- it publishes at most one pending comment per worker run, so comments are naturally spread across scheduled runs;
- it records queue and progress state in Google Sheets and is idempotent across retries.

Both workers run every 15 minutes through `.github/workflows/facebook-engagement-worker.yml` and `.github/workflows/linkedin-engagement-worker.yml`.

## Image identity and relevance

The editorial generator now chooses between:
- `REFERENCE_SUBJECT`: the actual reference photos are supplied to FLUX.2 as image inputs, and the final QA checks the subject's identity against those references;
- `CONTEXT_ONLY`: reference photos are not supplied, and the image must depict the legal situation itself without forcing the recurring lawyer into an unrelated scene.

Publication is blocked when final image QA fails. A failed image is regenerated only when the QA result is recoverable; otherwise the row remains in `NEEDS_IMAGE_REVIEW`.
