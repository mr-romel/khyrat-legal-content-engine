from evening_telegram_report import _acquisition_lines


def test_evening_report_separates_visits_clicks_and_actual_crm_leads():
    lines = _acquisition_lines({
        "period": {"start": "2026-11-10", "end": "2026-11-16"},
        "current": {"metrics": {"sessions": 120, "activeUsers": 98}},
        "events": [
            {"eventName": "contact_click", "eventCount": 14},
            {"eventName": "consultation_click", "eventCount": 8},
        ],
        "lead_crm": {
            "inquiries_received": 5,
            "qualified_leads": 3,
            "clients_confirmed": 1,
        },
    })
    text = "\n".join(lines)
    assert "جلسات الموقع: 120" in text
    assert "contact_click): 14" in text
    assert "consultation_click): 8" in text
    assert "الاستفسارات المسجلة في CRM: 5" in text
    assert "العملاء المحتملون المؤهلون: 3" in text
    assert "العملاء المؤكدون: 1" in text
    assert "الزيارة أو ضغطة التواصل ليست عميلًا" in text


def test_evening_report_does_not_turn_missing_events_into_fake_leads():
    lines = _acquisition_lines({
        "period": {"start": "2026-11-10", "end": "2026-11-16"},
        "current": {"metrics": {"sessions": None, "activeUsers": None}},
        "events": [],
        "lead_crm": {"inquiries_received": 0, "qualified_leads": 0, "clients_confirmed": 0},
    })
    text = "\n".join(lines)
    assert "جلسات الموقع: غير متاح" in text
    assert "لا توجد بيانات أحداث بعد" in text
    assert "الاستفسارات المسجلة في CRM: 0" in text
