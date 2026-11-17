# Free Egyptian-Arabic Reel Pilot (isolated)

This experiment is deliberately isolated from the production publishing pipeline. It does not publish to Facebook, Instagram, LinkedIn, Blogger, Telegram, or write to Google Sheets.

## Stack
- Manim Community + FFmpeg for 9:16 animated scenes and final MP4 muxing.
- VoiceTut-TTS for local Egyptian-Arabic narration (Apache-2.0 project; model weights download at first run).
- Pillow + arabic-reshaper + python-bidi for deterministic RTL slide text.
- Google Sheets API with read-only scope, solely to select the next future scheduled row.

## Run locally
Install FFmpeg, Python 3.10, and the packages from `requirements.txt`; install OmniVoice as documented by VoiceTut-TTS. Set `GOOGLE_SERVICE_ACCOUNT_JSON` (or `GOOGLE_CREDENTIALS`) and `GOOGLE_SHEET_ID`. Then:

```bash
python pilot.py --output-dir out
```

A smoke render without Google credentials can use an explicit topic:
```bash
python pilot.py --topic "بنود لازم تراجعها قبل توقيع عقد العمل في مصر" --demo-content "راجع مدة العقد والأجر وطبيعة العمل وساعات العمل والإجازات وآلية إنهاء العلاقة، واحتفظ بنسخة موقعة." --output-dir out
```

## Safety gates
- The Sheet adapter is read-only and refuses to guess a row if no future scheduled row can be parsed.
- The pilot only creates local artifacts; no social publishing secrets are passed to the workflow.
- The video is 1080x1920 (9:16), H.264/AAC MP4, with Arabic text rendered as shaped slide images to avoid broken RTL glyphs.
- Review the spoken Arabic, source facts, and visual pacing before considering integration. This is a pilot, not legal advice or approval to publish.

## GitHub test
Run the manual-only workflow `Free Arabic Reel Pilot (manual review only)` on this branch. It uploads the MP4, narration, script, and QA metadata as an artifact. There is no cron schedule and no publish step.
