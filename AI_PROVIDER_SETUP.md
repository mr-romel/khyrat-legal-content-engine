# Alternate AI provider setup

The text-generation router tries providers in this order:

1. Gemini (GEMINI_API_KEY)
2. Groq (GROQ_API_KEY)
3. Cerebras (CEREBRAS_API_KEY)
4. OpenRouter free-model router (OPENROUTER_API_KEY)

When Gemini reports quota exhaustion/rate limiting, it is skipped for the rest of that worker process and the next configured provider is attempted. Provider free quotas, model availability, and terms can change; this is best-effort failover, not a guarantee of unlimited free inference. The image-generation path is separate and still needs its configured image provider.

## Create keys

- Groq: https://console.groq.com/keys
- OpenRouter: https://openrouter.ai/settings/keys — the free tier currently documents a limited daily allowance for free models.
- Cerebras: https://cloud.cerebras.ai/ — use only if your account dashboard confirms an available $0/free allowance; current plans and promotional credits may vary.

Do not paste keys into source files, commits, issue comments, or chat.

## Add GitHub Actions secrets

Open https://github.com/mr-romel/khyrat-legal-content-engine/settings/secrets/actions and create these Repository secrets. Add the value for each provider you want enabled:

- GROQ_API_KEY
- OPENROUTER_API_KEY
- CEREBRAS_API_KEY (optional)

The workflows already map these secrets into the scheduled publisher, Blogger publisher, Facebook and LinkedIn engagement workers, daily Reel generator, and content-intelligence job. Missing provider keys are skipped automatically.

## Current default model IDs

- Groq: openai/gpt-oss-120b (override with GROQ_MODEL)
- Cerebras: gpt-oss-120b (override with CEREBRAS_MODEL)
- OpenRouter: openrouter/free (override with OPENROUTER_MODEL)

## Blogger OAuth check

After generating a fresh local authorized-user JSON with scripts/blogger_oauth.py, update the repository secret BLOGGER_OAUTH_JSON manually. Then open Actions → Blogger OAuth Read-only Check → Run workflow. This check refreshes the token and reads accessible blogs; it does not publish an article.

Automatic persistence of refreshed OAuth JSON into GitHub Secrets requires a valid GH_SECRET_ROTATION_TOKEN with permission to update repository Actions secrets. If that token is absent, the OAuth check can still validate the current credentials but cannot update the secret automatically.
