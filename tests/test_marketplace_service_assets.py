from marketplace.service_assets import build_khamsat_package


def test_khamsat_package_is_publish_ready_for_review():
    service = {
        "title": "مراجعة العقود التجارية",
        "description": "مراجعة قانونية عملية للعقد وتحديد المخاطر والبنود التي تحتاج تعديلاً.",
        "deliverables": ["ملاحظات قانونية", "تعديلات مقترحة"],
    }
    package = build_khamsat_package(service)
    assert package["review_status"] == "READY_FOR_REVIEW"
    assert len(package["requirements"]) >= 3
    assert len(package["faq"]) >= 3
    assert len(package["upgrades"]) >= 2
    assert package["deliverables"] == service["deliverables"]
