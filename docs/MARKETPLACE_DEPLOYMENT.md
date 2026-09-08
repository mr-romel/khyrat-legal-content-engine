# Marketplace Dashboard Deployment

## Current architecture

The Marketplace dashboard keeps the existing Python server as the application layer. `api/index.py` adapts the same routes for a serverless deployment and uses Cloudflare D1 when its environment variables are configured. Without D1 configuration, the adapter falls back to the existing local JSON state store.

## Vercel

The repository contains `vercel.json` and `api/index.py` for Vercel Python deployment. No Render configuration is required.

Required runtime variables for persistent cloud state:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_D1_DATABASE_ID`
- `CLOUDFLARE_API_TOKEN`

The GitHub Actions test suite verifies the adapter and the existing Marketplace suite remains the gate before deployment.

## Cloudflare D1

The adapter creates/uses a single `marketplace_state` row containing the Marketplace state as JSON. This intentionally preserves the existing state model instead of introducing a second application data model during migration.

## Safety

Khamsat/Mostaql authentication, scraping, and automatic submission are not enabled by this adapter. Opportunity capture and submission remain human-controlled until an official supported integration is verified.

## Verification

Before considering a deployment ready:

1. Run the full Marketplace pytest suite.
2. Run the Quality Check workflow.
3. Confirm the Marketplace workflow builds the review dashboard and daily execution plan.
4. Configure Vercel environment variables only after creating the D1 database and token.
5. Verify `/api/health`, `/api/state`, and `/api/action` on the deployed URL.
