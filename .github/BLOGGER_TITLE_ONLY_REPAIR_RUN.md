# Blogger title-only repair run

One-time trigger for the validated live-post repair worker. Inventory LIVE posts from Blogger's public JSON feed, parse each exact post ID, repair only missing or nearly empty article bodies, upload an illustration, and verify the saved body and image with Blogger REST get by post ID.

The Blogger REST posts.list endpoint currently returns HTTP 400, so this repair uses the public feed for inventory and exact-ID REST patch/get for repairs.
Repair requested on 2026-10-19 after the post-ID parsing fix.
