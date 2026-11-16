# Blogger Conversion and Measurement Upgrade

## Conversion-focused service pages

The Blogger site setup now includes dedicated, reader-first service pages for:
- legal services for individuals and businesses;
- labor disputes and employee entitlements;
- contract review and drafting;
- corporate legal services and company formation;
- civil compensation and liability.

Each page describes scope, useful intake information, and a direct WhatsApp contact route. Copy avoids guaranteed outcomes and makes clear that a message is only an initial inquiry, not acceptance of a legal mandate. The pages are defined in `src/blogger_site_setup.py` and are not published by this change alone. The existing Blogger Pages workflow publishes or updates them only when its workflow is run after the change reaches the configured branch.

## GA4 reporting

The read-only report is implemented in `src/ga4_reporting.py` and scheduled by `.github/workflows/ga4-website-performance.yml`.

- GA4 property: `497002086`
- Site: `https://askmahmoudkhyrat.blogspot.com/`
- Uses the existing `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_CREDENTIALS` secret.
- Requires that the service-account email has at least Viewer access to the GA4 property and that the Google Analytics Data API is enabled.
- Requests the last complete seven days and the preceding seven days, plus acquisition channels, page paths, and event names.
- Missing metric rows are `null`, not zero.
- GA4 page performance is not attributed to individual Search Console queries; key events are not treated as confirmed clients.

No GA4 measurement ID is embedded in the Blogger theme by this reporting job. The GA4 property ID is not the same thing as a web-stream Measurement ID (the `G-...` value). Actual contact conversion tracking requires the web-stream Measurement ID and a confirmed event implementation in the live Blogger theme.

## Deployment boundary

This change only prepares repository code and a scheduled read-only report. It does not update the live Blogger theme, publish pages, alter posts, change campaigns, or modify credentials. Review and merge the pull request first. Run the Blogger Pages workflow separately only after approving live page publication.
