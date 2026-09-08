"""Marketplace dashboard content layer.

Adds editable/copy-ready Khamsat service and Mostaql portfolio assets without
changing the existing Marketplace workflow or platform-account behavior.
"""
from __future__ import annotations

from marketplace import pro_dashboard as legacy

KHAMSAT_SERVICE = {
    "title": "سأراجع عقدك قانونيًا وأحدد المخاطر والبنود التي تحتاج تعديل مع تقديم الصياغة البديلة",
    "category": "خدمات قانونية واستشارات → استشارات قانونية / مراجعة العقود",
    "description": """هل لديك عقد وتريد معرفة المخاطر الموجودة فيه قبل التوقيع؟

سأقوم بمراجعة العقد قانونيًا بشكل عملي، مع التركيز على البنود التي قد تسبب لك التزامات أو خسائر أو مشاكل مستقبلية.

تشمل المراجعة:
• مراجعة بنود العقد بندًا بندًا.
• تحديد البنود غير الواضحة أو التي قد تحمل مخاطر قانونية.
• التنبيه إلى الالتزامات والجزاءات والشروط غير المتوازنة.
• مراجعة بنود الدفع والمدة والتجديد والإنهاء.
• مراجعة المسؤولية والتعويضات والشرط الجزائي.
• مراجعة السرية والملكية الفكرية عند وجودها.
• تحديد البنود التي تحتاج إلى تفاوض أو تعديل.
• اقتراح صياغة بديلة للبنود المهمة التي تحتاج تعديلًا.

وفي النهاية ستحصل على ملاحظات واضحة وعملية تساعدك على معرفة:
ما المشكلة؟ وما خطورتها؟ وما التعديل المقترح؟

الخدمة مناسبة لمراجعة العقود والاتفاقيات التجارية والمدنية وعقود العمل وغيرها، حسب طبيعة المستند.

يرجى إرسال العقد قبل الطلب إذا كان المستند طويلًا أو غير معتاد، للتأكد من ملاءمته لنطاق الخدمة.""",
    "basic": "مراجعة عقد حتى 5 صفحات + تحديد المخاطر الأساسية.",
    "upgrade_1": "مراجعة عقد حتى 10 صفحات + ملاحظات تفصيلية.",
    "upgrade_2": "مراجعة كاملة + صياغة البدائل المقترحة.",
    "upgrade_3": "مراجعة + إعادة صياغة البنود + مناقشة مختصرة لأهم الملاحظات.",
    "thumbnail": """الصورة المصغرة لخمسات:
النص الرئيسي: راجع عقدك قبل ما توقّع
النص الثانوي: كشف المخاطر + تعديل البنود
الهوية: اسأل محمود / خيرت للمحاماة
التصميم: عقد حقيقي المظهر عليه علامات مراجعة قانونية، تصميم احترافي نظيف، بدون ميزان محكمة أو صور Stock مزدحمة، وبدون نصوص كثيرة.""",
}

PORTFOLIO = [
    {
        "title": "مراجعة وتحليل عقد تجاري وتحديد المخاطر القانونية",
        "summary": "Case Study تطبيقي يوضح تحليل بنود الدفع والمسؤولية والجزاءات والإنهاء والتعويض والتعديلات المقترحة.",
        "body": """التحدي:
العميل لديه عقد تجاري ويريد توقيعه لكنه غير متأكد من حجم الالتزامات التي يتحملها.

ما تم عمله:
مراجعة البنود المتعلقة بالدفع، المسؤولية، الجزاءات، الإنهاء، والتعويض، مع تحديد نقاط عدم التوازن والصياغات التي قد تسمح بتفسير واسع.

المخاطر المكتشفة:
التزامات غير متوازنة، ونقاط تحتاج إلى تفاوض قبل التوقيع.

الحل:
اقتراح تعديلات محددة وإعادة صياغة البنود الأكثر تأثيرًا.

النتيجة:
تصور واضح للمخاطر والتعديلات المطلوبة قبل التوقيع.""",
    },
    {
        "title": "صياغة عقد تجاري متوازن يحمي مصالح العميل",
        "summary": "نموذج يوضح بناء عقد من الصفر وفق طبيعة التعامل وتوزيع الحقوق والالتزامات والمخاطر.",
        "body": """الهدف:
إنشاء عقد واضح وقابل للتنفيذ بدل الاعتماد على نموذج عام لا يعكس طبيعة الصفقة.

المنهج:
تحديد طبيعة العلاقة، نطاق العمل، المقابل المالي، المواعيد، المسؤولية، الإنهاء، السرية، والتعويضات.

المخرج:
صياغة منظمة تقلل مناطق الغموض وتوضح حقوق والتزامات كل طرف.""",
    },
    {
        "title": "مراجعة عقد عمل وتحليل الالتزامات والجزاءات وإنهاء العلاقة",
        "summary": "Case Study تطبيقي لمراجعة عقد عمل من منظور المخاطر والالتزامات والشروط التي تستدعي الانتباه.",
        "body": """التحدي:
مراجعة عقد عمل قبل التوقيع وفهم الالتزامات العملية المترتبة عليه.

ما تم عمله:
تحليل بنود الأجر، مدة العقد، الالتزامات، الجزاءات، السرية، الإنهاء، وأي شروط غير واضحة أو غير متوازنة.

النتيجة:
تقرير عملي يحدد النقاط المهمة والتعديلات المقترحة قبل اتخاذ القرار.""",
    },
    {
        "title": "تحليل قانوني لمستندات شركة وتحديد المخاطر قبل اتخاذ القرار",
        "summary": "نموذج Legal Due Diligence مصغر يركز على اكتشاف المخاطر القانونية وتحويلها إلى نقاط قرار واضحة.",
        "body": """المطلوب:
تقييم مجموعة من المستندات القانونية قبل الدخول في تعامل أو اتخاذ قرار تجاري.

التحليل:
تحديد الالتزامات، المخاطر التعاقدية، نقاط التعارض، والمستندات التي تحتاج إلى استكمال أو مراجعة.

المخرج:
قائمة مخاطر مرتبة حسب الأهمية مع توصيات عملية للتعامل معها.""",
    },
]


def _box(title: str, body: str, ident: str) -> str:
    e = legacy.e
    return (
        '<article class="asset-box">'
        f'<div class="asset-head"><h3>{e(title)}</h3>'
        f'<button class="btn primary" onclick="copyAsset(\'{ident}\')">نسخ بالكامل</button></div>'
        f'<textarea id="{ident}" class="asset-text">{e(body)}</textarea>'
        '</article>'
    )


def _assets_panel() -> str:
    e = legacy.e
    svc = (
        f"العنوان:\n{KHAMSAT_SERVICE['title']}\n\n"
        f"التصنيف:\n{KHAMSAT_SERVICE['category']}\n\n"
        f"الوصف:\n{KHAMSAT_SERVICE['description']}\n\n"
        f"الباقة الأساسية:\n{KHAMSAT_SERVICE['basic']}\n\n"
        f"تطوير 1:\n{KHAMSAT_SERVICE['upgrade_1']}\n\n"
        f"تطوير 2:\n{KHAMSAT_SERVICE['upgrade_2']}\n\n"
        f"تطوير 3:\n{KHAMSAT_SERVICE['upgrade_3']}\n\n"
        f"الصورة المصغرة:\n{KHAMSAT_SERVICE['thumbnail']}"
    )
    portfolio = "\n\n".join(
        f"{i+1}. {x['title']}\n{x['summary']}\n\n{x['body']}" for i, x in enumerate(PORTFOLIO)
    )
    thumb = KHAMSAT_SERVICE["thumbnail"]
    boxes = _box("خمسات — الخدمة الجاهزة للنسخ", svc, "khamsat-service")
    boxes += _box("خمسات — نص الصورة المصغرة / Brief", thumb, "khamsat-thumbnail")
    for i, item in enumerate(PORTFOLIO, 1):
        boxes += _box(f"مستقل — Portfolio #{i}: {item['title']}", f"العنوان:\n{item['title']}\n\nالوصف المختصر:\n{item['summary']}\n\nCase Study:\n{item['body']}", f"portfolio-{i}")
    return (
        '<section class="panel" id="marketplace-assets">'
        '<div class="head"><div><h2>أصول خمسات ومستقل — جاهزة للمراجعة والنسخ</h2>'
        '<div class="muted">راجع النص هنا أولًا، ثم اضغط «نسخ بالكامل» والصقه مباشرة في المنصة.</div></div>'
        '<span class="badge">COPY READY</span></div>'
        '<div class="notice">الخدمة مكتوبة للبيع المباشر، والـPortfolio مكتوب كحالات تطبيقية. لا يوجد ادعاء بعملاء أو نتائج حقيقية غير موثقة.</div>'
        '<div class="asset-grid">' + boxes + '</div></section>'
    )


def render(s, mobile=False):
    page = legacy.render(s, mobile)
    if mobile:
        return page
    css = """<style>.asset-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.asset-box{background:#f8fafc;border:1px solid #e4e7ec;border-radius:12px;padding:12px}.asset-head{display:flex;justify-content:space-between;align-items:center;gap:8px}.asset-head h3{font-size:14px;margin:0}.asset-text{min-height:220px;background:#fff}.asset-box .btn{white-space:nowrap}@media(max-width:760px){.asset-grid{grid-template-columns:1fr}}</style>"""
    js = """<script>async function copyAsset(id){const x=document.getElementById(id);try{await navigator.clipboard.writeText(x.value);alert('تم نسخ المحتوى بالكامل');}catch(e){x.focus();x.select();document.execCommand('copy');alert('تم نسخ المحتوى بالكامل');}}</script>"""
    marker = '</main>'
    if marker in page:
        page = page.replace('</head>', css + '</head>', 1)
        page = page.replace(marker, _assets_panel() + marker, 1)
        page = page.replace('</script></body>', '</script>' + js + '</body>', 1)
    return page


# Reuse the proven HTTP/action layer; only replace rendered desktop HTML.
legacy.render = render
main = legacy.main

if __name__ == "__main__":
    main()
