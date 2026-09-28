# Blogger publishing setup

The engine now has an isolated Blogger publisher for:
- `https://askmahmoudkhyrat.blogspot.com/`
- search-derived Arabic titles using Google Suggest signals;
- human-style long-form article HTML;
- Article/BlogPosting JSON-LD;
- topic labels;
- related internal links from recent Blogger posts;
- fixed WhatsApp/Facebook/LinkedIn/Blogger contact footer;
- downloadable HTML/TXT/JSON publishing packages;
- generated image retention in the repository/artifact package.

## Required GitHub secrets

Add:
- `BLOGGER_ENABLED=true`
- `BLOGGER_OAUTH_JSON=<Google OAuth authorized-user JSON with refresh_token>`
- optionally `BLOGGER_BLOG_ID=<Blogger blog id>`
- `BLOGGER_URL=https://askmahmoudkhyrat.blogspot.com/`

The OAuth credential must have the Blogger scope:
`https://www.googleapis.com/auth/blogger`

The existing Google service-account credential continues to be used only for Google Sheets.

## Search/indexing

Blogger supplies the publishing surface; Google Search Console remains the monitoring/indexing layer. Submit the Blogger sitemap in Search Console:
`https://askmahmoudkhyrat.blogspot.com/sitemap.xml`

If static Blogger Pages are used, also submit:
`https://askmahmoudkhyrat.blogspot.com/sitemap-pages.xml`

The system does not promise indexing or ranking. It prepares crawlable, structured, internally linked content and records the search-derived title signal used for each article.

## Production flow

Social publisher -> persist generated image/assets -> Blogger worker -> update Google Sheet with Blogger URL/title/query -> upload the publishing package as a GitHub Actions artifact.

Blogger failure is retryable and does not erase a successful Facebook/LinkedIn publication.
