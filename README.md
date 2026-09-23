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
