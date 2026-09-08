# Marketplace Rollout Checklist

## Phase 1 — Core

- Marketplace core state and service catalog remain isolated from Core.
- Opportunity scoring, queue transitions, review, follow-up, revenue analytics, notifications, and discovery are covered by automated tests.

## Phase 2 — Control center

- Dashboard exposes service catalog, opportunities, due follow-ups, portfolio, activity, and manual actions.
- No platform login, scraping, or automatic proposal submission is performed.

## Phase 3 — CI gate

- Marketplace workflow runs the complete Marketplace test suite.
- It builds the review dashboard artifact.
- It builds the daily execution plan.
- Quality Check remains a separate production gate.

## Phase 4 — Cloud readiness

- Vercel adapter is present at `api/index.py`.
- Cloudflare D1 state adapter is present at `src/marketplace/cloud_state.py`.
- `vercel.json` routes all requests through the adapter.
- Local JSON state remains the fallback when D1 variables are absent.

## Phase 5 — Production activation

This phase requires external provider account configuration and cannot be completed solely through the GitHub repository connection. Once Vercel and Cloudflare credentials are configured, verify the health, state, and action endpoints before treating the public dashboard as live.

## Current rule

Do not sacrifice the working scheduled Publisher or Core Content Engine while activating Marketplace. Marketplace deployment must remain isolated from publishing behavior.
