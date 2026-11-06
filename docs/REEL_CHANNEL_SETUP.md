# Reel publishing channels and required secrets

The reel publishing workflow is designed to publish to Facebook and YouTube. LinkedIn is not a target for reels. TikTok support is implemented as an optional, separately authorized publisher and should remain disabled until the developer app and account have the required approval.

## YouTube Shorts

Create a Google Cloud OAuth client for a Desktop/Web application and enable YouTube Data API v3. Authorize the channel with the scope `https://www.googleapis.com/auth/youtube.upload`, then create a refresh token for that same OAuth client. Add these repository Actions secrets:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Optional repository variable/secret: `YOUTUBE_PRIVACY_STATUS` (defaults to `public`; use `private` for the first end-to-end test). The uploader appends `#Shorts` to the title and records the returned video ID and URL. Google may apply API quota or unverified-app restrictions.

## First-party comments on Reels and Shorts

The approved publishing workflow adds a stable, per-video bundle of 3-5 comments to each newly published Facebook Reel and YouTube Short. The bundle contains a topic-specific question, a cautious practical answer, and a CTA linking to the exact Blogger article URL saved on the same Google Sheets content row. Optional fourth/fifth comments vary between a practical CTA and another audience question.

Facebook uses the existing Page access token and `publish_facebook_video_comment` endpoint. YouTube comments require a separate refresh token because the upload-only OAuth grant does not automatically include comment permissions.

After authorizing the same channel with this additional scope:

`https://www.googleapis.com/auth/youtube.force-ssl`

add this repository Actions secret:

- `YOUTUBE_COMMENT_REFRESH_TOKEN`

Keep `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` unchanged. Do not paste refresh tokens into source code or chat. If the secret is absent, YouTube comment publication is recorded as partial and retried by the 15-minute workflow without re-uploading the Short or duplicating already recorded comments.

Comment tracking columns are appended to the Content sheet:
- `Reel Facebook Comments Status`
- `Reel Facebook Comment IDs`
- `Reel YouTube Comments Status`
- `Reel YouTube Comment IDs`

Comments remain queued until the same content row has `Blogger Status=PUBLISHED` and a valid post URL on `askmahmoudkhyrat.blogspot.com`. This prevents unrelated or homepage links from being posted.

## TikTok

Register an app at TikTok for Developers, configure Login Kit and Content Posting API, request/obtain the `video.publish` scope, and authorize the target TikTok account. Add:

- `TIKTOK_ACCESS_TOKEN`

Optional: `TIKTOK_PRIVACY_LEVEL`. The code defaults to `SELF_ONLY` until you explicitly configure an allowed public privacy level. TikTok app review, creator eligibility, and posting caps can restrict public posting. This publisher is not wired into automatic publishing by default; enable it only after the app and account are approved.

## Subtitle timing

The subtitle renderer is in `src/reel_subtitles.py`. It accepts a JSON array of timed sentences, for example:

```json
{
  "segments": [
    {"text": "الجملة الأولى المنطوقة.", "start": 0.0, "end": 2.8},
    {"text": "الجملة الثانية المنطوقة.", "start": 2.8, "end": 5.4}
  ]
}
```

The generation workflow must pass sentence timings from the narration/TTS output to the renderer. The utility deliberately does not estimate sentence timings from the text, because that would desynchronize captions from the spoken audio. The box is horizontal, in the lower third, and renders one sentence at a time. It uses Arial Bold if installed and DejaVu Sans Bold as a Linux fallback.
