# Blogger title-only repair run

One-time trigger for the validated live-post repair worker. The repair worker inventories LIVE posts from Blogger's public JSON feed (the REST posts.list endpoint currently returns HTTP 400), repairs only posts with missing or nearly empty article bodies, uploads an illustration, and verifies the saved body and image by exact post ID.

Repair requested on 2026-10-19 after the Blogger post-ID persistence fix and Google Trends topic expansion.
