# Khyrat Marketplace Control Center

## تشغيله

على Windows: افتح `run_marketplace_dashboard.bat`.

سيعمل Dashboard محليًا على:

`http://127.0.0.1:8765`

وسيتم فتح المتصفح تلقائيًا.

## الوصول من الموبايل خارج البيت

للوصول الآمن من أي مكان، نفّذ إعداد Cloudflare مرة واحدة باستخدام `setup_marketplace_remote.bat` ثم شغّل نفس Launcher المعتاد.

التصميم:

`PC → localhost → Cloudflare Tunnel → Cloudflare Access → Mobile`

لا يوجد Port Forwarding.

## دورة العمل

1. الخدمة تُجهّز لخمسات.
2. Portfolio samples تُجهّز.
3. فرصة مستقل تُلصق في Dashboard.
4. النظام يحسب Match Score وAcquisition Score.
5. النظام يولد العرض.
6. Quality Check يفحص العرض.
7. أنت تراجع.
8. أنت تعتمد أو ترفض.
9. الإرسال/النشر على المنصة يظل يدويًا حتى تتوفر وسيلة رسمية مدعومة وآمنة.

## قاعدة الأمان

بيانات Marketplace التشغيلية لا تُنشر على GitHub Pages. لا تضع أي Tunnel token أو كلمة مرور أو API key داخل Git.
