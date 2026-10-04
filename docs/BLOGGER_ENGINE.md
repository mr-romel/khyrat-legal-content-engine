# Khyrat Legal Content Engine — Blogger Intelligence Layer

Blogger is a channel inside the existing engine, not a separate project.

Operating loop:
Content creation → Blogger publishing → Search Console observation → Keyword Map → Opportunity/Refresh → article update or supporting article → internal links → measurement → monetization.

Implemented:
- Search Console query/page ingestion.
- Dynamic Keyword Map with query, page, clicks, impressions, CTR, position, intent and action.
- Opportunity detection for positions 8–20, high-impression/low-CTR pages, and promising queries with weak coverage.
- Refresh queue to reduce cannibalization and avoid blindly creating a page for every query.
- Related-topic scoring from the live Blogger corpus.
- Optional automatic internal-link insertion using existing published URLs only.
- Foundation pages: About, Disclaimer, Privacy, Contact, Topic Index.
- Service-intent mapping for future lead generation and monetization.

Required:
- SEARCH_CONSOLE_SITE_URL must be a Search Console property accessible to the Google service account.
- BLOGGER_OAUTH_JSON is the existing Blogger user OAuth credential.
- GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID remain the existing Sheet credentials.

Safety:
The intelligence layer does not invent legal sources. Search data is used to discover demand, not to manufacture legal rules. New legal articles should continue through the existing legal editorial/review gate.

AdSense:
The engine prepares the content, trust pages, search intelligence and monetization mapping. AdSense approval, publisher identity, ad code and theme settings require the real AdSense account and are not fabricated by automation.

Primary objective:
Build topical authority around Egyptian legal questions by answering the searcher's question directly, covering related questions, maintaining a coherent internal knowledge graph, and continuously refreshing pages using observed search demand.
