# Khyrat Legal Content Engine V2 — Setup

## Production schedule

- 14:00 Cairo
- 20:00 Cairo
- The Sheet date/time remains authoritative.
- Failed/partial posts are retried automatically after the scheduled post.

## Telegram Control Center

Create a bot with BotFather and add these GitHub Actions secrets:

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- TELEGRAM_ADMIN_USER_ID

The bot receives BLOCK notifications and provides Approve/Reject buttons. Approval changes only the affected row to APPROVED; the production pipeline remains independent.

## Facebook automatic renewal

Add:

- FACEBOOK_APP_ID
- FACEBOOK_APP_SECRET
- FACEBOOK_USER_ACCESS_TOKEN
- FACEBOOK_PAGE_ACCESS_TOKEN
- GH_SECRET_ROTATION_TOKEN

The long-lived User Access Token is used as the renewal source. When the Page/User token is within 14 days of expiry, the token manager refreshes the User token when possible, obtains a fresh Page token through /me/accounts, validates it, and updates the GitHub secrets.

## LinkedIn automatic renewal

If the LinkedIn application is eligible for programmatic refresh tokens, add:

- LINKEDIN_CLIENT_ID
- LINKEDIN_CLIENT_SECRET
- LINKEDIN_REFRESH_TOKEN
- LINKEDIN_TOKEN_EXPIRES_AT

The token manager refreshes when the access token has 14 days or less remaining. If LinkedIn does not grant programmatic refresh to the application, Telegram reports that manual OAuth renewal is required.

## GitHub secret rotation token

Create a fine-grained PAT restricted to this repository with the minimum repository permission required to write Actions secrets. Store it as GH_SECRET_ROTATION_TOKEN. It is used only by token-health.yml to update encrypted repository secrets.

## New data stores

The engine creates these Google Sheet tabs automatically:

- PostBank — every fully published post becomes reusable source material.
- Analytics — publication/objective/pillar/comment counts and platform IDs.

## Human review model

- CLEAR: automatic publish.
- REVIEW: automatic publish + Telegram advisory; does not stop normal operation.
- BLOCK: row becomes NEEDS_REVIEW and Telegram sends the full content/reason plus Approve/Reject controls. Other scheduled runs continue normally.

## Failure recovery

If Facebook fails and LinkedIn succeeds, the row becomes PARTIAL_FAILED. The next run skips the already-published LinkedIn post and retries only Facebook. The same applies in reverse.

## Android future

The current GitHub Actions version is intentionally a backend/core-engine design. When Android is introduced, the recommended architecture is:

Android app -> API/backend -> encrypted token store -> Facebook/LinkedIn/Telegram/Google/Gemini.

The Android app should never store Facebook App Secret, LinkedIn Client Secret, or long-lived refresh credentials. Token renewal remains a backend responsibility. The Android app only displays token health and starts a secure OAuth reauthorization flow when a provider requires manual consent.
