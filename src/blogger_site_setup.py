from __future__ import annotations

import html
import json
import os
import re
from typing import Any

from blogger_publisher import BloggerPublishError, blog_id, service
from config import load_blogger_config

SITE_NAME = "اسأل محمود | محمود خيرت - محامٍ ومستشار قانوني للأفراد والشركات"
SITE_ALTERNATE_NAME = "اسأل محمود"
BLOG_URL = "https://askmahmoudkhyrat.blogspot.com/"
WHATSAPP = "https://wa.me/201022718375"
FACEBOOK = "https://www.facebook.com/AskMahmoudNow"
LINKEDIN = "https://www.linkedin.com/in/mahmoud-khyrat"
YOUTUBE = "https://www.youtube.com/channel/UCc6NY-Y6w7can5GdTtLVtMA"
LEGAL_PHONE_E164 = os.getenv("LEGAL_PHONE_E164", "+201022718375").strip()

PAGES: list[dict[str, str]] = [
    {
        "title": "من نحن",
        "slug": "about-us",
        "content": """<article><script type=\"application/ld+json\">%s</script><h1>اسأل محمود - محامٍ ومستشار قانوني للأفراد والشركات</h1><p>منصة قانونية مصرية تقدم محتوى عمليًا للأفراد وأصحاب الأعمال والشركات، يشرح الحقوق والالتزامات والإجراءات القانونية بلغة واضحة، ويربط القاعدة القانونية بالوقائع والمستندات والمخاطر العملية.</p><p>نعالج موضوعات القانون المدني والتعويضات، والقضايا الجنائية، والأسرة والأحوال الشخصية، والقضايا العمالية، وتأسيس الشركات وصياغة العقود، ومنازعات الشركات والتجارة، والاستشارات القانونية.</p><h2>نطاق تقديم الخدمات</h2><p>متابعة القضايا والحضور والترافع في القاهرة والجيزة، مع إتاحة الاستشارات القانونية أونلاين للأفراد والشركات في جميع محافظات مصر. استقبال العملاء بالحجز المسبق، والاستفسار الأولي مجاني، أما الاستشارة التفصيلية ومراجعة المستندات فتكون بمقابل وفق طبيعة الموضوع.</p><h2>عن محمود خيرت</h2><p>محمود خيرت رجب محامٍ ومستشار قانوني، يهتم بتقديم شرح قانوني دقيق وعملي يساعد الأفراد والشركات على فهم الموقف القانوني وتقييم الخيارات قبل اتخاذ القرار.</p><h2>تواصل</h2><p><a href=\"%s\">واتساب</a> · <a href=\"%s\">فيسبوك</a> · <a href=\"%s\">لينكدإن</a> · <a href=\"%s\">يوتيوب</a></p><p><a href=\"https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html\">الهوية الرسمية لمدونة اسأل محمود ومحمود خيرت رجب</a></p></article>""" % (json.dumps({"@context":"https://schema.org","@type":"ProfilePage","mainEntity":{"@type":"Person","name":"محمود خيرت رجب","alternateName":["محمود خيرت","اسأل محمود","Ask Mahmoud"],"jobTitle":"محامٍ ومستشار قانوني للأفراد والشركات","description":"محتوى وخدمات قانونية في مصر للأفراد والشركات تشمل المدني والجنائي والأسرة والعمل والشركات والعقود والمنازعات والاستشارات","url":BLOG_URL,"sameAs":[BLOG_URL,FACEBOOK,LINKEDIN,YOUTUBE]}},ensure_ascii=False), WHATSAPP, FACEBOOK, LINKEDIN, YOUTUBE),
    },
    {
        "title": "تواصل معنا",
        "slug": "contact",
        "content": """<article><h1>تواصل مع اسأل محمود</h1><p>للاستفسارات العامة أو طلب التواصل بشأن موقف قانوني، يمكن استخدام قنوات التواصل التالية.</p><ul><li><a href=\"%s\">واتساب مباشر</a></li><li><a href=\"%s\">صفحة فيسبوك</a></li><li><a href=\"%s\">لينكدإن</a></li><li><a href=\"%s\">قناة يوتيوب</a></li></ul><p>عند التواصل بشأن واقعة قانونية، يفيد إرسال ملخص زمني للوقائع والمستندات ذات الصلة بدل الاكتفاء بعنوان المشكلة.</p></article>""" % (WHATSAPP, FACEBOOK, LINKEDIN, YOUTUBE),
    },
    {
        "title": "إخلاء المسؤولية القانونية",
        "slug": "legal-disclaimer",
        "content": """<article><h1>إخلاء المسؤولية القانونية</h1><p>المحتوى المنشور في هذه المدونة لأغراض التوعية والمعلومات القانونية العامة، ولا يُعد في ذاته استشارة قانونية مخصصة أو رأيًا قانونيًا نهائيًا بشأن واقعة بعينها.</p><p>التقييم القانوني يختلف باختلاف الوقائع والمستندات والصفة القانونية والاختصاص والمواعيد والإجراءات والتعديلات التشريعية والقضائية ذات الصلة.</p><p>لا ينبغي اتخاذ قرار أو بدء إجراء قانوني اعتمادًا على مقال عام فقط. عند وجود واقعة فعلية أو نزاع أو عقد أو إجراء له أثر قانوني، يجب مراجعة المستندات والظروف الخاصة بالحالة مع المختص.</p><p>رغم الحرص على الدقة وتحديث المحتوى، لا نضمن أن كل مادة تظل محدثة لكل تعديل قانوني أو قضائي بعد تاريخ نشرها.</p></article>""",
    },
    {
        "title": "سياسة الخصوصية",
        "slug": "privacy-policy",
        "content": """<article><h1>سياسة الخصوصية</h1><p>نحترم خصوصية زوار المدونة. هذه الصفحة توضح بصورة عامة كيفية التعامل مع المعلومات التي قد يشاركها الزائر عند استخدام المدونة أو التواصل معنا.</p><h2>المعلومات التي يرسلها الزائر</h2><p>إذا تواصلت معنا عبر البريد أو واتساب أو منصات التواصل، فقد تتلقى قنوات التواصل البيانات التي تختار إرسالها. يُرجى عدم إرسال كلمات مرور أو بيانات بطاقات الدفع أو مستندات هوية غير مطلوبة.</p><h2>ملفات الارتباط والتحليلات</h2><p>قد تستخدم المنصة أو خدماتها ملفات ارتباط وتقنيات قياس لتحسين الأداء وفهم الاستخدام، وفق الإعدادات والسياسات المطبقة على الخدمة.</p><h2>مشاركة البيانات</h2><p>لا نبيع البيانات الشخصية لمعلنين. قد تُعالج البيانات لدى مزودي الخدمات التقنية اللازمة لتشغيل المنصة عندما يكون ذلك مطلوبًا لتقديم الخدمة.</p><h2>التحديثات</h2><p>قد يتم تحديث هذه السياسة عند الحاجة لتعكس تغييرات تشغيلية أو قانونية.</p></article>""",
    },
    {
        "title": "فهرس الموضوعات القانونية",
        "slug": "legal-topics",
        "content": """<article><h1>فهرس الموضوعات القانونية</h1><p>استخدم هذا الفهرس للوصول إلى الموضوعات القانونية المنشورة في المدونة. سيتم توسيعه مع نشر مقالات جديدة.</p><ul><li>القضايا المدنية والتعويضات والمسؤولية المدنية</li><li>القضايا الجنائية والإجراءات الجنائية</li><li>الأسرة والأحوال الشخصية</li><li>القضايا العمالية وحقوق العامل وصاحب العمل</li><li>تأسيس الشركات وصياغة العقود</li><li>منازعات الشركات والتجارة والعقود التجارية</li><li>الاستشارات القانونية للأفراد والشركات</li><li>الإيجارات والإخطارات والإجراءات والدعاوى</li></ul><p>لأفضل نتيجة في البحث، ابدأ بالسؤال القانوني المحدد أو راجع المقال الأقرب إلى الواقعة والمستندات محل البحث.</p></article>""",
    },
    {
        "title": "هوية اسأل محمود",
        "slug": "ask-mahmoud-identity",
        "content": """<article><script type="application/ld+json">{"@context":"https://schema.org","@type":"ProfilePage","url":"https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html","mainEntity":{"@type":"Person","@id":"https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html#person","name":"محمود خيرت رجب","alternateName":["محمود خيرت","محمود خيرت المحامي","اسأل محمود","إسأل محمود","Ask Mahmoud"],"jobTitle":"محامٍ ومستشار قانوني للشركات","url":"https://askmahmoudkhyrat.blogspot.com/p/blog-page_03.html","sameAs":["https://www.facebook.com/AskMahmoudNow","https://www.linkedin.com/in/mahmoud-khyrat","https://www.youtube.com/channel/UCc6NY-Y6w7can5GdTtLVtMA","https://askmahmoudkhyrat.blogspot.com/"],"knowsAbout":["القانون المصري","القضايا المدنية والتعويضات","القضايا الجنائية","الأحوال الشخصية والأسرة","قانون العمل","تأسيس الشركات","العقود التجارية","المنازعات التجارية","الاستشارات القانونية"]}}</script><h1>اسأل محمود | محمود خيرت رجب</h1><p>اسأل محمود هي المنصة القانونية التوعوية المرتبطة بمحمود خيرت رجب، المحامي والمستشار القانوني للأفراد والشركات في مصر. تشمل مجالات المحتوى والخدمات القضايا المدنية والتعويضات، والقضايا الجنائية، والأسرة والأحوال الشخصية، والعمل، والشركات والعقود، والمنازعات التجارية، والاستشارات القانونية. متابعة القضايا والحضور والترافع في القاهرة والجيزة، والاستشارات أونلاين في جميع محافظات مصر.</p><p>وقد يبحثون عن صاحب المحتوى بصيغ: محمود خيرت، محمود خيرت رجب، ومحمود خيرت المحامي. هذه الصيغ تشير إلى الاسم والهوية التعريفية المستخدمة في المنصة.</p><h2>الروابط الرسمية</h2><ul><li><a href="%s">مدونة اسأل محمود</a></li><li><a href="%s">صفحة اسأل محمود على فيسبوك</a></li><li><a href="%s">ملف محمود خيرت على لينكدإن</a></li><li><a href="%s">قناة اسأل محمود على يوتيوب</a></li></ul><p>المحتوى المنشور للتوعية القانونية العامة ولا يمثل استشارة مخصصة لحالة بعينها.</p></article>""" % (BLOG_URL, FACEBOOK, LINKEDIN, YOUTUBE),
    },
    {
        "title": "الخدمات القانونية للأفراد والشركات",
        "slug": "legal-services",
        "content": """<article><h1>خدمات قانونية للأفراد والشركات في مصر</h1><p>يقدم مكتب الأستاذ محمود خيرت خدمات قانونية للأفراد وأصحاب الأعمال والشركات، مع تحديد نطاق العمل والأتعاب والمستندات المطلوبة قبل بدء أي تكليف.</p><h2>خدمات الأفراد</h2><ul><li>القضايا المدنية والتعويضات والمطالبات المالية.</li><li>القضايا العمالية ومستحقات العامل ومنازعات صاحب العمل.</li><li>القضايا الجنائية والجنح ومراجعة الموقف الإجرائي.</li><li>الأحوال الشخصية ومنازعات الأسرة وفق المستندات والاختصاص.</li></ul><h2>خدمات الشركات</h2><ul><li>تأسيس الشركات ومراجعة مستنداتها وإجراءاتها.</li><li>صياغة ومراجعة عقود الخدمات والتوريد والشراكة والعمل.</li><li>إدارة المخاطر التعاقدية ومراجعة الالتزامات والجزاءات.</li><li>المنازعات التجارية والمدنية ومطالبات الشركات.</li></ul><h2>نطاق العمل</h2><p>متابعة القضايا والحضور والترافع في القاهرة والجيزة، والاستشارات القانونية عن بُعد للأفراد والشركات في جميع محافظات مصر، بحسب طبيعة الخدمة والاختصاص.</p><h2>اطلب تقييمًا أوليًا</h2><p>أرسل ملخصًا مختصرًا للوقائع، وتاريخ الواقعة، والصفة القانونية، والمرحلة الحالية، ونوع المستندات المتاحة. لا ترسل أصول المستندات أو بيانات شديدة الحساسية في رسالة أولى.</p><p><a href="%s?text=أرغب%20في%20طلب%20تقييم%20أولي%20لموقف%20قانوني">اطلب التواصل عبر واتساب</a></p><p>لا تُعد الرسالة وحدها قبولًا للتوكيل أو بدءًا في مباشرة إجراء، ولا تنشأ علاقة مهنية إلا بعد الاتفاق على نطاق التكليف.</p></article>""".replace("%s", WHATSAPP),
    },
    {
        "title": "محامي قضايا العمل ومستحقات العامل في مصر",
        "slug": "labor-lawyer-egypt",
        "content": """<article><h1>خدمات قانونية في قضايا العمل ومستحقات العامل في مصر</h1><p>تحتاج منازعات العمل إلى مراجعة عقد العمل، وطبيعة العلاقة، ومدة الخدمة، والأجر الفعلي، وسبب انتهاء العلاقة، والمراسلات والمستندات المتاحة.</p><h2>موضوعات المراجعة</h2><ul><li>الفصل وإنهاء عقد العمل والادعاء بالفصل التعسفي.</li><li>الأجور المتأخرة والعمولات والعمل الإضافي.</li><li>مقابل رصيد الإجازات ومستحقات نهاية الخدمة بحسب القانون المنطبق.</li><li>الاستقالة ومدى صحتها وآثارها.</li><li>التأمينات الاجتماعية ومنازعات إثبات مدة العمل والأجر.</li></ul><h2>المستندات التي تساعد في التقييم</h2><p>عقد العمل، ومفردات المرتب أو التحويلات، وبيان التأمينات، وخطاب إنهاء الخدمة أو الاستقالة، وكشوف الحضور، والمراسلات ذات الصلة. تختلف القائمة بحسب الواقعة.</p><h2>اطلب مراجعة موقفك</h2><p>اذكر تاريخ بدء العمل، وآخر يوم عمل، والأجر، وسبب انتهاء العلاقة، وما إذا كان قد تم تحرير شكوى أو دعوى بالفعل.</p><p><a href="%s?text=أرغب%20في%20مراجعة%20موقف%20قانوني%20متعلق%20بعلاقة%20عمل">التواصل لطلب تقييم أولي عبر واتساب</a></p><p>لا يمكن تحديد الاستحقاق أو المواعيد دون مراجعة المستندات والتشريع الساري وتفاصيل الواقعة.</p></article>""".replace("%s", WHATSAPP),
    },
    {
        "title": "مراجعة وصياغة العقود للشركات والأفراد",
        "slug": "contract-review-drafting-egypt",
        "content": """<article><h1>مراجعة وصياغة العقود في مصر</h1><p>مراجعة العقد قبل التوقيع تساعد على كشف الالتزامات غير المتوازنة، ومخاطر التنفيذ، والثغرات المتعلقة بالمقابل والمدة والإنهاء والمسؤولية وتسوية النزاع.</p><h2>أنواع العقود</h2><ul><li>عقود تقديم الخدمات والتشغيل والاستشارات.</li><li>عقود التوريد والمقاولات والتوزيع.</li><li>عقود الشراكة والتعاون وعدم الإفصاح.</li><li>عقود العمل واللوائح والاتفاقات المرتبطة بها.</li><li>عقود البيع والإيجار والاتفاقات المدنية والتجارية.</li></ul><h2>ما الذي تتضمنه المراجعة؟</h2><p>تحديد الأطراف والصفة والتفويض، ووصف نطاق العمل والمخرجات، والمقابل وآلية السداد، والجدول الزمني، والضمانات، والتعويض والشرط الجزائي، والسرية والملكية الفكرية، والإنهاء وآثاره، والقوة القاهرة، والقانون الواجب التطبيق وتسوية المنازعات.</p><h2>قبل إرسال العقد</h2><p>وضح الطرف الذي تمثله، وهدف التعاقد، وما إذا كان العقد مسودة أم موقعًا، وأهم المخاطر التي تريد تجنبها. يمكنك حجب أرقام الهوية والحسابات والبيانات غير اللازمة.</p><p><a href="%s?text=أرغب%20في%20طلب%20مراجعة%20أو%20صياغة%20عقد">اطلب مراجعة عقد عبر واتساب</a></p></article>""".replace("%s", WHATSAPP),
    },
    {
        "title": "الخدمات القانونية للشركات وتأسيسها",
        "slug": "corporate-legal-services-egypt",
        "content": """<article><h1>مستشار قانوني للشركات والمؤسسات في مصر</h1><p>تحتاج الشركات إلى دعم قانوني وقائي لا يقتصر على معالجة النزاع بعد وقوعه؛ بل يبدأ من مراجعة التعاقدات والصلاحيات والإجراءات والالتزامات التنظيمية.</p><h2>نطاق الخدمات</h2><ul><li>مراجعة إجراءات تأسيس الشركات وتعديلاتها ومستنداتها.</li><li>صياغة ومراجعة العقود التجارية وعقود الخدمات والتوريد.</li><li>مراجعة قرارات الشركاء والجمعيات ومحاضر الاجتماعات والتفويضات.</li><li>مراجعة لوائح العمل والموارد البشرية ومنازعات العمل.</li><li>إدارة المطالبات والمنازعات المدنية والتجارية.</li><li>إعداد مذكرات المخاطر القانونية ومراجعة الالتزام التعاقدي.</li></ul><h2>كيف نبدأ؟</h2><p>يُحدد نطاق العمل بعد معرفة نشاط الشركة، وشكلها القانوني، والجهة أو الطرف المقابل، والمستندات القائمة، والنتيجة المطلوبة، والموعد الزمني.</p><p><a href="%s?text=نرغب%20في%20طلب%20خدمات%20استشارية%20قانونية%20للشركة">تواصل عبر واتساب بشأن خدمات الشركات</a></p><p>يتم تحديد الأتعاب ونطاق التكليف كتابةً قبل البدء في العمل.</p></article>""".replace("%s", WHATSAPP),
    },
    {
        "title": "قضايا التعويض والمسؤولية المدنية",
        "slug": "civil-compensation-lawyer-egypt",
        "content": """<article><h1>المساعدة القانونية في دعاوى التعويض والمسؤولية المدنية</h1><p>تقييم المطالبة بالتعويض يبدأ بتحديد الفعل أو الخطأ المنسوب، والضرر المدعى به، وعلاقة السببية، وأدلة كل عنصر، وأي دفوع أو مواعيد أو إجراءات مؤثرة.</p><h2>موضوعات شائعة</h2><ul><li>التعويض عن الأضرار المادية والأدبية.</li><li>المسؤولية عن الإخلال بالعقد.</li><li>التعويض عن الفعل الضار بحسب ظروف الواقعة.</li><li>المطالبات المالية الناشئة عن المعاملات المدنية والتجارية.</li></ul><h2>مستندات أولية</h2><p>العقود والمراسلات، ومحاضر الشرطة أو التحقيق إن وجدت، والتقارير الفنية والطبية بحسب نوع الضرر، والفواتير وإثباتات الخسارة، وأي أحكام أو إنذارات سابقة.</p><h2>اطلب تقييمًا للموقف</h2><p>أرسل وصفًا زمنيًا مختصرًا للواقعة، وتاريخ حدوث الضرر، والمستندات المتاحة، وما إذا كان قد تم اتخاذ إجراء قضائي.</p><p><a href="%s?text=أرغب%20في%20تقييم%20موقف%20قانوني%20بشأن%20دعوى%20تعويض">التواصل عبر واتساب لطلب تقييم أولي</a></p></article>""".replace("%s", WHATSAPP),
    },

]


SERVICE_CONVERSION_TITLES = {
    "الخدمات القانونية للأفراد والشركات",
    "محامي قضايا العمل ومستحقات العامل في مصر",
    "مراجعة وصياغة العقود للشركات والأفراد",
    "الخدمات القانونية للشركات وتأسيسها",
    "قضايا التعويض والمسؤولية المدنية",
}


def _apply_dual_contact_actions() -> None:
    """Add WhatsApp + phone CTAs and GA4 click-intent events to service pages."""
    phone = re.sub(r"[^0-9+]", "", LEGAL_PHONE_E164)
    if not phone:
        raise ValueError("LEGAL_PHONE_E164 must contain a callable phone number.")
    if not phone.startswith("+"):
        phone = "+" + phone
    for page in PAGES:
        content = str(page.get("content", "") or "")
        if page.get("title") == "تواصل معنا":
            whatsapp_anchor = f'<a href="{WHATSAPP}">واتساب مباشر</a>'
            tracked_whatsapp = (
                f'<a href="{WHATSAPP}" data-contact-method="whatsapp" data-service-page="contact" '
                'onclick="if(typeof window.gtag===&quot;function&quot;){window.gtag(&quot;event&quot;,&quot;contact_click&quot;,{contact_method:&quot;whatsapp&quot;,service_page:&quot;contact&quot;});}">واتساب مباشر</a>'
            )
            content = content.replace(whatsapp_anchor, tracked_whatsapp)
            phone_item = (
                f'<li><a href="tel:{phone}" data-contact-method="phone" data-service-page="contact" '
                'onclick="if(typeof window.gtag===&quot;function&quot;){window.gtag(&quot;event&quot;,&quot;contact_click&quot;,{contact_method:&quot;phone&quot;,service_page:&quot;contact&quot;});}">اتصال هاتفي مباشر</a></li>'
            )
            if "data-contact-method=\\\"phone\\\"" not in content:
                content = content.replace("</ul>", phone_item + "</ul>", 1)
            page["content"] = content
            continue
        if page.get("title") not in SERVICE_CONVERSION_TITLES:
            continue
        pattern = re.compile(r'<a href="(https://wa\.me/[^"]+)">([^<]+)</a>')
        match = pattern.search(content)
        if not match:
            raise ValueError(f"Missing WhatsApp CTA in managed service page: {page.get('title')}")
        whatsapp_url, whatsapp_label = match.groups()
        service_slug = re.sub(r"[^a-z0-9-]", "-", str(page.get("slug", "service"))).strip("-") or "service"
        block = (
            '<div class="khyrat-contact-actions" style="display:flex;flex-wrap:wrap;gap:10px;margin:18px 0">'
            f'<a class="khyrat-contact-button khyrat-whatsapp" data-contact-method="whatsapp" '
            f'data-service-page="{service_slug}" href="{whatsapp_url}" '
            f'onclick="if(typeof window.gtag===\'function\'){{window.gtag(\'event\',\'contact_click\',{{contact_method:\'whatsapp\',service_page:\'{service_slug}\'}});}}">'
            f'{whatsapp_label}</a>'
            f'<a class="khyrat-contact-button khyrat-phone" data-contact-method="phone" '
            f'data-service-page="{service_slug}" href="tel:{phone}" '
            f'onclick="if(typeof window.gtag===\'function\'){{window.gtag(\'event\',\'contact_click\',{{contact_method:\'phone\',service_page:\'{service_slug}\'}});}}">'
            'اتصل هاتفيًا الآن</a></div>'
        )
        page["content"] = content[:match.start()] + block + content[match.end():]


_apply_dual_contact_actions()


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _page_payload(page: dict[str, str]) -> dict[str, Any]:
    return {"title": page["title"], "content": page["content"]}


def main() -> int:
    config = load_blogger_config()
    if not config["enabled"]:
        print("Blogger disabled; site pages skipped.")
        return 0
    svc = service()
    bid = blog_id(svc, config["blogger_url"])
    existing: dict[str, dict[str, Any]] = {}
    token = None
    while True:
        kwargs = {"blogId": bid, "maxResults": 100}
        if token:
            kwargs["pageToken"] = token
        data = svc.pages().list(**kwargs).execute()
        for item in data.get("items", []) or []:
            existing[_norm(item.get("title", ""))] = item
        token = data.get("nextPageToken")
        if not token:
            break

    created = updated = 0
    for page in PAGES:
        key = _norm(page["title"])
        current = existing.get(key)
        payload = _page_payload(page)
        try:
            if current and str(current.get("id", "")).strip():
                current_content = str(current.get("content", ""))
                if _norm(current_content) != _norm(payload["content"]):
                    svc.pages().update(blogId=bid, pageId=str(current["id"]), body={**current, **payload}).execute()
                    updated += 1
                    print(f"Blogger page updated: {page['title']}")
                else:
                    print(f"Blogger page already current: {page['title']}")
            else:
                result = svc.pages().insert(blogId=bid, body=payload, isDraft=False).execute()
                created += 1
                print(f"Blogger page created: {page['title']} ({result.get('url','')})")
        except Exception as exc:
            print(f"Blogger page failed: {page['title']}: {exc}")
            raise
    print(f"Blogger site pages complete: created={created}, updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
