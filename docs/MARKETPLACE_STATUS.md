# Marketplace Status

The Marketplace MVP is currently CI-green on the `main` branch.

The production scheduled Publisher remains a separate system and must not be coupled to Marketplace deployment.

Marketplace is deployment-ready for Vercel + Cloudflare D1, but public activation still requires one-time external provider configuration because the available repository connection does not provision Vercel or Cloudflare accounts.

No Render dependency is required.

Platform automation boundary: the system may prepare, rank, review, and track opportunities, but it does not automatically log into, scrape, or submit to Khamsat or Mostaql.
