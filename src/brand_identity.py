"""Single source of truth for the Ask Mahmoud professional identity."""
from __future__ import annotations

BRAND_NAME = "اسأل محمود"
PROFESSIONAL_NAME = "محمود خيرت رجب"
PROFESSIONAL_TITLE = "محامٍ ومستشار قانوني في مصر"
BRAND_LOCKUP = f"{BRAND_NAME} | {PROFESSIONAL_NAME}"
BRAND_DESCRIPTOR = "خدمات قانونية للأفراد والشركات"
BRAND_SERVICE_AREA = "متابعة القضايا في القاهرة والجيزة | استشارات أونلاين في جميع محافظات مصر"
BRAND_PROFILE_BIO = (
    "محمود خيرت رجب، محامٍ ومستشار قانوني في مصر. خدمات قانونية للأفراد والشركات "
    "في القضايا المدنية والجنائية والأسرة والعمل والعقود ومنازعات الشركات. "
    "متابعة القضايا بالقاهرة والجيزة واستشارات أونلاين في جميع المحافظات."
)
BRAND_SLOGAN = "خليك فاكر دايما ... اسأل محمود"
BRAND_PRIMARY = (12, 28, 48)       # deep navy
BRAND_ACCENT = (190, 151, 76)     # muted legal gold
BRAND_WHITE = (255, 255, 255)
BRAND_OVERLAY_TEXT = "اسال محمود خيرت - محام ومستشار قانوني"
BRAND_OVERLAY_SUBTEXT = ""
FACEBOOK_BADGE_BLUE = (24, 119, 242)
BLOGGER_BADGE_GREEN = (76, 175, 80)
BRAND_PLATFORM_BADGES = ("facebook", "blogger")


def build_editorial_image_prompt(*, topic: str, post_context: str, visual_description: str) -> str:
    """Constrain generation to a concrete scene grounded in the actual post."""
    topic = " ".join(str(topic or "").split()).strip()
    context = " ".join(str(post_context or "").split()).strip()
    scene = " ".join(str(visual_description or "").split()).strip()
    if not scene:
        raise ValueError("A post-derived visual description is required.")
    # Put the concrete scene first. Downstream image providers may enforce a 2,048
    # character limit; never let broad style rules or long post text truncate the
    # actual subject the image must depict.
    return (
        "PRIMARY VISUAL BRIEF — FOLLOW THIS SCENE EXACTLY: "
        f"{scene[:720]}\n"
        f"LEGAL TOPIC: {topic[:140] or 'Not specified'}\n"
        "Create one photorealistic editorial image in a present-day Egyptian setting. "
        "Use contemporary 2020s architecture, infrastructure, clothing and materials. "
        "Keep the main subject large, clear and visually dominant, with natural lighting and realistic proportions. "
        "Do not replace the requested subject with a generic lawyer portrait, courthouse, scales, gavel, handshake or unrelated office. "
        "No readable text, letters, numbers, logos, seals, signatures, watermarks or invented legal documents. "
        "No ancient Egyptian, Pharaonic, archaeological, fantasy or historical imagery.\n"
        f"SHORT SOURCE CONTEXT: {context[:420] or 'Use only the primary visual brief.'}"
    )
