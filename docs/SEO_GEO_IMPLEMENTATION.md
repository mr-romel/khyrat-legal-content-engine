# Search / SEO / GEO implementation

## What is implemented

The engine now maintains a SearchGEO intelligence sheet linked to each published content row.

For each post it records:

- search intent;
- primary search question;
- related questions;
- jurisdiction;
- legal entity / practice area;
- concise answer extract;
- supporting evidence pointer;
- local intent;
- page type;
- SEO title;
- meta description;
- URL slug;
- GEO summary;
- author/provenance.

The metadata is generated during the existing content-intelligence publication record flow, so social publishing and search intelligence remain connected through the same Post ID / content lineage.

A backfill job is available at:

PYTHONPATH=src python scripts/run_search_geo.py

It writes missing SearchGEO records in one batch to reduce Google Sheets write pressure.

A scheduled GitHub Actions job runs the backfill daily.

## Important SEO/GEO design decision

This repository is primarily a social publishing/content engine. It does not currently contain a public legal-article website with a verified canonical domain, sitemap, robots policy, or web CMS.

Therefore this phase implements the Search/GEO intelligence layer without inventing a website URL or pretending that social posts themselves are an on-page SEO implementation.

The resulting metadata is the contract for a future web publisher:

Topic -> search intent -> primary question -> legal entity -> jurisdiction -> answer extract -> evidence -> related questions -> web article/FAQ -> internal links -> Search Console feedback.

## Google-aligned principles

The layer is designed around people-first, useful content; clear answers to real questions; crawlable web content when a web destination exists; accurate metadata; structured legal provenance; and local/jurisdiction context.

No special llms.txt dependency, AI-only schema, keyword stuffing, or page-per-query duplication is required by this architecture.

## Operational safety

Search/GEO metadata generation is non-blocking for publication. If metadata logging fails, the social publishing path should continue.

The SearchGEO sheet is idempotent by Post ID during normal publication and the backfill only adds missing Post IDs.

## Next web phase

When a real public legal-content domain/CMS is available, the same SearchGEO records can drive:

1. canonical URLs;
2. XML sitemap generation;
3. robots.txt;
4. Article / FAQ / Breadcrumb JSON-LD where applicable;
5. internal-link graph;
6. author and legal-source provenance blocks;
7. Search Console ingestion and feedback;
8. AI-search / generative-search measurement.

Those pieces should be attached to the actual web property rather than guessed inside the social-only repository.
