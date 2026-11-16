# Blogger Conversion and Measurement Upgrade

## Conversion-focused service pages

The Blogger site setup now includes dedicated, reader-first service pages for:
- legal services for individuals and businesses;
- labor disputes and employee entitlements;
- contract review and drafting;
- corporate legal services and company formation;
- civil compensation and liability.

Each page describes scope, useful intake information, and both WhatsApp and telephone contact routes. The CTAs emit a GA4 `contact_click` event with `contact_method` and `service_page` parameters when the existing `gtag` function is available. These are contact-intent events, not confirmed leads or clients. Copy avoids guaranteed outcomes and makes clear that a message is only an initial inquiry, not acceptance of a legal mandate. The phone default is the existing WhatsApp number; override it with `LEGAL_PHONE_E164` if voice calls use another number. The pages are defined in `src/blogger_site_setup.py` and are not published by this code change alone. The existing Blogger Pages workflow publishes or updates them only when its workflow is run after the change reaches the configured branch.

## GA4 reporting

The read-only report is implemented in `src/ga4_reporting.py` and scheduled by `.github/workflows/ga4-website-performance.yml`.

- GA4 property: `497002086`\n- Web-stream Measurement ID verified through the connected GA4 data: `G-SV9T6SC2TK`.
- Site: `https://askmahmoudkhyrat.blogspot.com/`
- Uses the existing `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_CREDENTIALS` secret.
- Requires that the service-account email has at least Viewer access to the GA4 property and that the Google Analytics Data API is enabled.
- Requests the last complete seven days and the preceding seven days, plus acquisition channels, page paths, and event names.
- Missing metric rows are `null`, not zero.
- GA4 page performance is not attributed to individual Search Console queries; key events are not treated as confirmed clients.

The live property currently records `page_view`, `session_start`, `first_visit`, and `user_engagement`, but the inspected period contained no contact-click events. The web-stream Measurement ID is known (`G-SV9T6SC2TK`). This change adds click-intent handlers to the managed service-page CTAs without inserting a second GA4 base tag or duplicating page views. Verify events in GA4 DebugView/Realtime after publication. Do not mark `contact_click` as a confirmed-client conversion; track actual qualified inquiries separately.

## Deployment boundary

This change only prepares repository code and a scheduled read-only report. It does not update the live Blogger theme, publish pages, alter posts, change campaigns, or modify credentials. Review and merge the pull request first. Run the Blogger Pages workflow separately only after approving live page publication.
