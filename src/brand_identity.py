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
    return (
        "Create one photorealistic editorial image for an Egyptian legal-awareness post. "
        "Depict the exact concrete action, object, document type, evidence, and setting in the visual brief; "
        "do not substitute a generic lawyer portrait, courthouse, scales, gavel, handshake, or stock office. "
        "Set the scene unmistakably in present-day Egypt in the 2020s: modern Cairo/Giza streets, contemporary apartments, ordinary current offices, current-model smartphones, laptops, cars, furniture, clothing, and materials. "
        "ABSOLUTE STYLE BAN: this is NOT ancient Egypt, NOT Pharaonic, NOT archaeological, NOT historical, NOT a period drama, and NOT a fantasy scene. "
        "Never show pyramids, sphinxes, obelisks, hieroglyphics, ancient temples, tombs, sarcophagi, mummies, pharaohs, royal crowns, ancient columns, papyrus, sandstone monuments, gold masks, ancient Egyptian motifs, or ornamental Pharaonic patterns. "
        "Do not use Egyptian heritage or ancient civilization as visual shorthand for modern Egypt. The legal issue must be shown in a normal contemporary urban environment. "
        "No readable text, letters, numbers, logos, seals, signatures, watermarks, or invented legal documents. "
        "Keep the main subject clear and visually dominant, with natural lighting and realistic proportions. "
        "The scene must communicate the specific issue without adding facts not present in the source.\n"
        f"LEGAL TOPIC: {topic or 'Not specified'}\n"
        f"SOURCE CONTEXT: {context or 'Use only the concrete visual brief below.'}\n"
        f"VISUAL BRIEF: {scene}"
    )
