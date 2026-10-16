# Free-tier AI provider setup

The text-generation router is configured to avoid Cerebras and any paid-model fallback:

1. Gemini API free tier (GEMINI_API_KEY) for core legal drafting/review.
2. Groq developer free tier (GROQ_API_KEY) for fallback and auxiliary tasks.
3. OpenRouter's free-model router (OPENROUTER_API_KEY, model defaults to openrouter/free).
4. Meta Model API (MODEL_API_KEY, model defaults to muse-spark-1.3) as an additional fallback.

When a provider reports quota exhaustion, an invalid key, or a connection failure, the router tries the next configured provider. Free-tier limits and model availability can change and are not unlimited. Keep each account on its free plan and do not enable billing if the requirement is a $0 ceiling. The image-generation path is separate and still needs its own provider; this text router does not make image generation free.

## Create keys

- Gemini AI Studio: https://aistudio.google.com/apikey — select a model and project that show free-tier access; do not attach billing if you need a hard $0 ceiling.
- Groq: https://console.groq.com/keys — use the free developer tier.
- OpenRouter: https://openrouter.ai/settings/keys — use only free models; its published free plan currently documents 50 requests/day. See https://openrouter.ai/pricing/.
- Meta Model API: https://dev.meta.ai/ — open the API keys section and create a key for your team. Official API docs: https://dev.meta.ai/docs/authentication. Meta's model availability, quotas, and pricing are account-dependent; do not assume this provider is free.

Do not paste keys into source files, commits, issue comments, or chat.

## Add GitHub Actions secrets

Open https://github.com/mr-romel/khyrat-legal-content-engine/settings/secrets/actions and create these Repository secrets. Add the value for each provider you want enabled:

- GROQ_API_KEY
- OPENROUTER_API_KEY
- MODEL_API_KEY

The workflows already map these secrets into the scheduled publisher, Blogger publisher, Facebook and LinkedIn engagement workers, daily Reel generator, and content-intelligence job. Missing provider keys are skipped automatically.

## Current default model IDs

- Groq: openai/gpt-oss-120b (override with GROQ_MODEL; subject to the Groq free-plan limits)
- OpenRouter: openrouter/free (do not override with a paid model if a $0 ceiling is required)
- Meta Model API: muse-spark-1.3 (override with META_MODEL if needed)

## Blogger OAuth check

After generating a fresh local authorized-user JSON with scripts/blogger_oauth.py, update the repository secret BLOGGER_OAUTH_JSON manually. Then open Actions → Blogger OAuth Read-only Check → Run workflow. This check refreshes the token and reads accessible blogs; it does not publish an article.

Automatic persistence of refreshed OAuth JSON into GitHub Secrets requires a valid GH_SECRET_ROTATION_TOKEN with permission to update repository Actions secrets. If that token is absent, the OAuth check can still validate the current credentials but cannot update the secret automatically.
