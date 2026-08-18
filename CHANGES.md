# Facebook Publisher integration

This patch connects the existing Khyrat Legal Content Engine to the Facebook Page publisher while keeping the Facebook integration isolated as a backend adapter.

## Files to add/change

1. Add `src/facebook_publisher.py` from this package.
2. Update `src/config.py` to read `FACEBOOK_PAGE_ACCESS_TOKEN`, with page ID `464216073916915` and Graph version `26.0` as defaults.
3. Update `src/main.py` to import `publish_photo()` and publish the generated JPEG after the content/image generation step. On success write:
   - `الحالة = PUBLISHED`
   - `Facebook Status = PUBLISHED`
   - `Facebook Post ID = <returned id>`
4. Update `requirements.txt` with:
   `requests>=2.32.0,<3.0.0`
5. Update `.github/workflows/publish.yml` so the run environment includes:
   `FACEBOOK_PAGE_ACCESS_TOKEN: ${{ secrets.FACEBOOK_PAGE_ACCESS_TOKEN }}`
   `FACEBOOK_PAGE_ID: "464216073916915"`
   `FACEBOOK_GRAPH_VERSION: "26.0"`

## Important behavior

- No Facebook token is stored in source code.
- The image is uploaded directly as multipart/form-data, so the post does not depend on a public image URL being available before the Facebook publish call.
- `NEEDS_REVIEW` items are not published automatically.
- Facebook errors are written to the existing `آخر خطأ` field and set `Facebook Status = FAILED`.
- The existing Google Sheet schema is preserved.
