from __future__ import annotations

import html
import json
import os
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
]


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
