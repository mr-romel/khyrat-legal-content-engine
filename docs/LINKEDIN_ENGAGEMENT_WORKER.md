# LinkedIn Engagement Worker

The LinkedIn publisher and engagement layer are intentionally separated.

## Flow

POST PUBLISHED -> Engagement Queue -> Delay -> Capability Check -> Generate Comment -> LinkedIn Comment API -> Success / Retry / Permission Block

The publisher does not create comments. A failure in the engagement worker cannot change a successful LinkedIn publication into a publishing failure.

## Queue

The worker creates a dedicated Google Sheets tab named `LinkedIn Engagement`. Each event is idempotent by:

`COMMENT:<post_urn>:1`

Only one first-party comment is scheduled automatically per published post. The design leaves room for a second event later without changing the publisher.

## Permission awareness

The worker probes the LinkedIn comments endpoint with a synthetic post URN. It never intentionally creates a real comment during the capability probe.

HTTP 403 is recorded as `BLOCKED_PERMISSION` and rechecked after 24 hours. Temporary/network failures use bounded retries.

LinkedIn's current documentation states that `w_member_social_feed` permits a member to post, comment, and react on posts on behalf of that member, while `w_member_social` is the post/comment/like permission listed by the Posts API. The Comments API specifically lists `w_member_social_feed` for member social actions. Verify the actual scopes granted to the OAuth token before enabling production engagement.

## Dry run

Run the `LinkedIn Engagement Dry Run` GitHub Action. It generates the comment, runs the capability probe, and records the proposed comment without sending it.

## Production

The `LinkedIn Engagement Worker` runs every 15 minutes. It reads successful LinkedIn posts from the existing Content sheet and maintains the queue independently.

No token or secret is written to the repository.
