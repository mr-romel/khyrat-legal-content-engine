from __future__ import annotations

import re
import os
from google import genai


def _clean(text: str) -> str:
    text = re.sub(r"(?i)\b(?:topic|angle|status|row|post_id)\s*[:=].*?(?=\.|\n|$)", "", text)
    text = re.sub(r"زاوية\s*(?:جديدة|المحتوى)?\s*[:：-]?", "", text)
    text = re.sub(r"اسم\s*الموضوع\s*[:：-]?", "", text)
    return " ".join(text.split()).strip()


def build_script(topic: str, approved_post: str, max_words: int = 180) -> str:
    """Create a concise spoken Egyptian-Arabic version of the whole approved post."""
    text = _clean(approved_post)
    if not text:
        raise ValueError("approved_post is required")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    client = genai.Client(api_key=key)
    prompt = f"""
أنت كاتب ومقدم محتوى قانوني مصري محترف.
حوّل المنشور القانوني المعتمد أدناه إلى نص يصلح لريل مدته تقريبًا 60 إلى 75 ثانية.

قواعد إلزامية:
- اللهجة مصرية طبيعية ومفهومة، مش فصحى مترجمة ولا لغة كتابية.
- النص يتقال بصوت إنسان مصري: جمل قصيرة، إيقاع طبيعي، وقفات منطقية.
- اختصر المنشور لكن غطّي كل أفكاره القانونية الأساسية، وما تسقطش نقطة جوهرية.
- ممنوع إضافة أي معلومة قانونية أو استنتاج غير موجود في المنشور.
- ممنوع ذكر اسم الموضوع أو الزاوية كبيانات إدارية.
- ممنوع عبارات مثل: "في هذا المنشور" أو "زاوية جديدة".
- ابدأ بخطاف مباشر، ثم الشرح، ثم خلاصة عملية قصيرة.
- من 150 إلى {max_words} كلمة تقريبًا.
- أعد النص فقط بدون عناوين أو علامات اقتباس.

المنشور المعتمد:
{text}
"""
    response = client.models.generate_content(model=model, contents=prompt)
    result = _clean(getattr(response, "text", ""))
    words = result.split()
    if len(words) < 120:
        raise RuntimeError("Gemini returned a Reel script that is too short.")
    return " ".join(words[:max_words]).strip()
