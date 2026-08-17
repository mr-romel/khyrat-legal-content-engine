# Khyrat Legal Content Engine

هذه النسخة هي النواة الخلفية للمشروع، ومصممة لتكون قابلة للتوسع لاحقًا إلى تطبيق Android.

## التشغيل التلقائي
يعمل GitHub Actions مرتين يوميًا:
- 10:00 صباحًا
- 20:00 مساءً
بتوقيت `Africa/Cairo`.

يوجد أيضًا تشغيل يدوي من GitHub Actions.

## Gemini
النموذج الافتراضي:
`gemini-3.5-flash-lite`

لا يستخدم المشروع `response_format` أو `response_schema` في هذه النسخة.
يطلب من Gemini JSON عاديًا ثم يتحقق منه محليًا، لتقليل اختلافات إصدارات SDK.

## Secrets
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_RANGE` = `Content!A:Q`
- `GEMINI_API_KEY`
- `GEMINI_MODEL` = `gemini-3.5-flash-lite`
