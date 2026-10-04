from __future__ import annotations
import os
from typing import Any
from blogger_publisher import blog_id, service

PAGES=[
{"title":"من نحن","content":"<h1>من نحن</h1><p>مدونة اسأل محمود تقدم محتوى قانونيًا مبسطًا للقارئ المصري، مع التركيز على شرح القاعدة القانونية والوقائع والمستندات والخطوات العملية.</p><p>المحتوى للتوعية العامة ولا يغني عن مراجعة الحالة الفردية ومستنداتها واختصاصها.</p>"},
{"title":"إخلاء المسؤولية","content":"<h1>إخلاء المسؤولية</h1><p>المحتوى المنشور للتوعية العامة وليس استشارة قانونية فردية. تختلف النتيجة باختلاف الوقائع والمستندات والتاريخ والاختصاص والنصوص السارية.</p><p>لا تعتمد على مقال منفرد لاتخاذ إجراء قد يترتب عليه حق أو التزام أو ميعاد قانوني دون مراجعة الحالة الفعلية.</p>"},
{"title":"سياسة الخصوصية","content":"<h1>سياسة الخصوصية</h1><p>نحترم خصوصية زوار المدونة. قد تستخدم المدونة أدوات قياس الزيارات والإعلانات والخدمات الخارجية وفق إعداداتها وسياساتها.</p><p>لا ترسل بيانات شخصية أو مستندات حساسة عبر التعليقات.</p>"},
{"title":"تواصل معنا","content":"<h1>تواصل معنا</h1><p>للاستفسارات العامة أو طلب تقييم أولي للموقف، استخدم قناة التواصل الرسمية المرتبطة بالمدونة.</p><p><a href=\"https://wa.me/201022718375\" rel=\"nofollow noopener\">التواصل عبر واتساب</a></p>"},
{"title":"فهرس الموضوعات القانونية","content":"<h1>فهرس الموضوعات القانونية</h1><p>هذا الفهرس يتوسع مع نشر المقالات الجديدة. استخدم البحث داخل المدونة للوصول إلى السؤال القانوني الأقرب لمشكلتك.</p><p>عند وجود مشكلة متعددة الجوانب، اقرأ أكثر من مقال ثم راجع الوقائع والمستندات قبل اتخاذ الإجراء.</p>"}
]

def _find(svc,bid,title)->dict[str,Any]|None:
    data=svc.pages().list(blogId=bid,status="all",fetchBodies=False,maxResults=100).execute()
    wanted=title.strip().casefold()
    for item in data.get("items",[]) or []:
        if str(item.get("title","")).strip().casefold()==wanted: return item
    return None

def upsert_pages(dry_run: bool=False)->list[dict[str,str]]:
    svc=service(); bid=blog_id(svc,os.getenv("BLOGGER_URL","").strip()); results=[]
    for page in PAGES:
        existing=_find(svc,bid,page["title"]); body={"title":page["title"],"content":page["content"]}
        if dry_run: results.append({"title":page["title"],"action":"DRY_RUN"}); continue
        if existing:
            page_id=str(existing.get("id","")).strip()
            svc.pages().patch(blogId=bid,pageId=page_id,body=body).execute()
            svc.pages().publish(blogId=bid,pageId=page_id).execute()
            results.append({"title":page["title"],"action":"UPDATED"})
        else:
            svc.pages().insert(blogId=bid,body=body,isDraft=False).execute()
            results.append({"title":page["title"],"action":"CREATED"})
    return results
