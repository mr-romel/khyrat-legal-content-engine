# Marketplace Dashboard — Remote Mobile Access

The Marketplace dashboard is designed for remote use without opening a router port or exposing the origin directly.

Architecture:

`Windows PC -> local Marketplace server (127.0.0.1:8765) -> cloudflared outbound tunnel -> Cloudflare Access -> your phone/browser`

The dashboard remains local on the Windows machine. Cloudflare Tunnel creates an outbound connection; no inbound router port forwarding is required. Cloudflare Access sits in front of the application and requires an approved login before the dashboard is reachable.

## One-time setup

1. Create/sign in to a Cloudflare account and add a domain to Cloudflare.
2. In Cloudflare Zero Trust, create a Tunnel named `khyrat-marketplace`.
3. Install `cloudflared` on the Windows machine that runs the Marketplace dashboard.
4. Add a published application route pointing your chosen hostname to `http://localhost:8765`.
5. Create a Cloudflare Access application for that hostname and add an Allow policy for your own email address. One-time PIN login is supported if you do not want to configure another identity provider.
6. Enable the tunnel connector on Windows and copy its tunnel token.
7. Double-click `setup_marketplace_remote.bat` in this repository. It saves the token and protected URL to Windows user environment variables; nothing is written to GitHub.
8. Close and reopen Command Prompt.
9. Double-click `run_marketplace_dashboard.bat`.

After that, the same launcher starts the local dashboard and the Cloudflare tunnel. From outside the house, open the protected HTTPS URL on the phone and authenticate through Cloudflare Access.

## Security rules

- Never use a public unauthenticated Quick Tunnel for this dashboard.
- Never commit the tunnel token, `.env`, Cloudflare credentials, or `marketplace_data/`.
- Do not enable router port forwarding for port 8765.
- Keep the Access policy restricted to the owner's email address.
- The dashboard performs state-changing actions, so the hostname must remain behind Access.

## Current Marketplace boundary

The dashboard can prepare services, portfolio items, opportunities, and offers, then route them through human approval. It does not automatically publish services to Khamsat or submit offers to Mostaql because no verified official write API has been established for those actions.
