# Blogger Organic Growth Loop

This workflow joins the live public Blogger audit with the connected Google Search Console property. It runs daily in Africa/Cairo time and can be run manually.

## Seven connected workstreams

1. **Search demand:** use observed Search Console queries and page performance. The workflow does not invent query volume when Google returns no query rows.
2. **Search intent and content clusters:** preserve the existing Blogger demand worker and keyword map; use query/page evidence to distinguish informational, procedural and commercial intent.
3. **Content quality and legal trust:** retain the existing article-review process, source verification and human legal review. No unverified statutory article, penalty, deadline or case is generated as fact.
4. **Technical SEO:** audit the live feed, real article URLs, HTTP status, title, meta description, canonical, H1, image alt, noindex, sitemap coverage and internal links.
5. **Internal linking:** retain the conservative link planner and separately controlled apply workflow. The planner must not add weak or unrelated links.
6. **GEO and structured answers:** keep direct answers, clear question headings, jurisdiction, author/provenance and source context in the existing SearchGEO metadata pipeline. Structured data is added only where it accurately describes visible page content.
7. **Measurement and iteration:** export date-bounded Search Console page/query metrics, page priorities and technical findings as a 90-day artifact. Compare equivalent date windows before claiming gains.

## Safety and interpretation

- Search Console's latest two days are excluded because they may be incomplete.
- Query privacy and low volume can result in no query rows. That is not proof of zero searches.
- Sitemap API/connector summaries are not treated as the public sitemap itself; the live XML is parsed by the technical audit.
- The workflow is read-only against Blogger. It does not bulk-rewrite or delete legal articles.
- The existing internal-link apply workflow creates a full backup and report before making its conservative, idempotent changes.
- A passing test or green workflow is not evidence of more organic traffic. Only dated Search Console clicks, impressions, CTR and position can demonstrate search performance.
