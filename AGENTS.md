# Repository-wide engineering rules

## Safety and production behavior
- Never commit credentials, tokens, API keys, OAuth refresh tokens, service-account JSON, or private user data. Read secrets only from environment variables / GitHub Secrets. Never print secret values; availability checks may print booleans only.
- Do not weaken legal-source verification, image semantic QA, approval gates, duplicate prevention, or idempotency to make a workflow green.
- A successful workflow must mean its intended work actually happened. A skipped/no-op workflow must report an explicit skipped/no-work outcome, not a misleading production success.
- Keep production publication behind explicit approval and preserve immutable source IDs and artifact fingerprints.

## Egyptian legal content
- Legal claims must be jurisdiction-specific and supported by reliable, topic-matched sources. Prefer primary official Egyptian legislation, official gazettes, courts, ministries, and public authorities.
- Do not invent article numbers, case numbers, session dates, legal quotations, or effective dates. Distinguish statutory text from summaries and commentary.
- When official source retrieval is unavailable, fail closed unless a traceable, pre-verified source is explicitly allowed by policy.

## Reels and media
- Remotion is the only approved Reel video compositor.
- Do not add Python/Pillow/local-drawing video generation or Edge TTS. Do not use robotic system voices. Use approved neural TTS providers only.
- Every Reel must be unique, topic-matched, visually QA-approved, and tied to its exact source row. Never send an old MP4 with new metadata.
- Never use generic or off-topic stock imagery as a fallback. Keep provider retries bounded and quota-aware.

## Workflows and testing
- Use least-privilege workflow permissions and pass only the secrets needed by each job.
- Add regression tests for every bug fix, including negative/failure-path tests.
- Do not make tests pass by deleting meaningful assertions or replacing behavioral checks with source-string checks.
- Keep generated artifacts, caches, backups, and dependencies out of review scope unless the change specifically affects them.
