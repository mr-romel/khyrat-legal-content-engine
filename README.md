# Khyrat Legal Content Engine

نظام مجاني مبني على GitHub Actions + Google Sheets + Gemini API + Python.

## 1) Google Sheet

أنشئ Spreadsheet جديد، وأعد تسمية أول Sheet إلى:

`Content`

ضع هذه العناوين في الصف الأول:

ID | الموضوع | تاريخ النشر | ساعة النشر | نوع الجدولة | الحالة | المحتوى | وصف الصورة | رابط الصورة (GitHub Raw) | Facebook Status | LinkedIn Status | Facebook Post ID | LinkedIn Post ID | آخر خطأ | وقت آخر تشغيل | المصادر القانونية | ملاحظات

### أنواع الجدولة الحالية

- `DATE_TIME`: نشر مرة واحدة في التاريخ والساعة المحددين.
- `DAILY`: يوميًا من تاريخ البداية، في الساعة المحددة.
- `DAILY_ODD`: كل يوم فردي من تاريخ البداية.
- `DAILY_EVEN`: كل يوم زوجي من تاريخ البداية.

### مثال

ID:
`001`

الموضوع:
`هل إيصال الأمانة يضمن استرداد الفلوس؟`

تاريخ النشر:
`2026-08-17`

ساعة النشر:
`20:00`

نوع الجدولة:
`DATE_TIME`

الحالة:
`READY`

المصادر القانونية:
اتركها فارغة في مرحلة الاختبار.

## 2) Google Cloud

- أنشئ Google Cloud Project.
- فعّل Google Sheets API.
- أنشئ Service Account.
- أنشئ JSON Key للخدمة.

شارك Google Sheet مع بريد الـService Account بصلاحية Editor.

Google Sheets API official quickstart:
https://developers.google.com/workspace/sheets/api/quickstart/python

## 3) Gemini

أنشئ API Key من Google AI Studio:

https://aistudio.google.com/apikey

النموذج الافتراضي:

`gemini-2.5-flash`

يمكن تغييره من GitHub Secret باسم:

`GEMINI_MODEL`

Google توثّق حاليًا استخدام Google GenAI SDK عبر حزمة `google-genai`.
https://ai.google.dev/gemini-api/docs/migrate

## 4) GitHub Secrets

من:
Repository → Settings → Secrets and variables → Actions

أضف:

### GOOGLE_SERVICE_ACCOUNT_JSON
الصق محتوى ملف JSON كاملًا.

### GOOGLE_SHEET_ID
هو الجزء الموجود في رابط Google Sheet بين `/d/` و`/edit`.

مثال:
https://docs.google.com/spreadsheets/d/ABC123XYZ/edit

القيمة:
`ABC123XYZ`

### GOOGLE_SHEET_RANGE

ضع:

`Content!A:Q`

### GEMINI_API_KEY

ضع مفتاح Gemini.

### GEMINI_MODEL

ضع:

`gemini-2.5-flash`

## 5) التشغيل

بعد رفع الملفات:

Actions → Khyrat Legal Content Engine → Run workflow

أول اختبار يدوي.

إذا نجح:
- تم قراءة الشيت.
- تم اختيار الموضوع المستحق.
- تم إنشاء المحتوى.
- تم إنشاء الصورة.
- تم تحديث الحالة.

الحالة المتوقعة:

`READY_FOR_SOCIAL_PUBLISH`

إذا وُجدت مراجعة قانونية مطلوبة:

`NEEDS_REVIEW`

## 6) الصورة

الصورة التي ينشئها Python تحفظ داخل مجلد `generated/` في المستودع.
بعد انتهاء الـWorkflow يتم Commit تلقائيًا للصورة حتى يظل رابطها صالحًا للاستخدام
في مراحل Facebook/LinkedIn اللاحقة.

## 7) GitHub Schedule

Workflow يعمل كل 5 دقائق.

الوقت الحقيقي يتحدد من Python باستخدام:

`Africa/Cairo`

وبالتالي لا نعتمد على فرق UTC في منطق اختيار المنشور.

## 8) مهم

هذه النسخة لا تنشر على Facebook أو LinkedIn بعد.
هي مرحلة تثبيت الـCore Engine.

بعد نجاحها سنضيف:
- Facebook Page API
- Facebook comment
- LinkedIn Posts API
- LinkedIn image upload
- LinkedIn reaction
- حالات SUCCESS / PARTIAL_FAILURE
- منع التكرار الكامل
- Log مفصل
