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
