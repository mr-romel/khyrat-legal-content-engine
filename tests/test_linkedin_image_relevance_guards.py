from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import free_media
import run_main


def test_wikimedia_relevance_filter_rejects_unrelated_map():
    query = "contemporary open plan office bathed in natural light"
    title = "File:Carte de la Basse-Egypte et de la province du Fayoum.jpg"
    description = "Historical map of Lower Egypt and the Fayoum province."
    assert not free_media._scene_metadata_matches_query(query, title, description)


def test_wikimedia_relevance_filter_accepts_matching_scene_terms():
    query = "modern office interior with meeting room"
    title = "File:Modern office interior meeting room.jpg"
    assert free_media._scene_metadata_matches_query(query, title)


def test_wikimedia_does_not_download_irrelevant_search_result(monkeypatch, tmp_path):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "query": {
                    "pages": [{
                        "title": "File:Carte de la Basse-Egypte et de la province du Fayoum.jpg",
                        "imageinfo": [{
                            "mime": "image/jpeg",
                            "thumburl": "https://example.invalid/map.jpg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "Public domain"},
                                "ImageDescription": {"value": "Historical map of Lower Egypt."},
                            },
                        }],
                    }]
                }
            }

    def fake_get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(free_media.requests, "get", fake_get)
    result = free_media.fetch_wikimedia_images(
        ["contemporary open plan office bathed in natural light"],
        tmp_path,
        target=1,
    )
    assert result == []
    assert calls == [free_media.WIKIMEDIA_API]


def test_linkedin_overlength_is_rewritten_as_complete_copy_not_truncated(monkeypatch):
    original = "نص قانوني طويل " * 250
    compact = (
        "تحتاج الإدارة إلى ربط القرار بالوقائع والمستندات قبل التنفيذ. "
        "وتبدأ المراجعة بتحديد الالتزام والمسؤول عنه والأثر القانوني والتشغيلي لكل بديل. "
        "كما يجب توثيق الإجراءات ومراجعة أي تحفظات أو استثناءات قبل اعتماد القرار. "
        "بهذا الأسلوب تستطيع الشركة تقليل مخاطر النزاع واتخاذ قرار مستنير."
    )
    captured = {}

    def fake_generate(**kwargs):
        captured["prompt"] = kwargs["previous_context"]
        return {"post": compact}

    monkeypatch.setattr(run_main, "_diverse_generate_post", fake_generate)
    result = run_main._fit_linkedin_char_limit(
        original,
        api_key="test",
        model="test-model",
        topic="المساهمة الجنائية",
        legal_sources="",
    )
    assert result == compact
    assert len(result) <= 2600
    assert "no more than the stated character limit" in captured["prompt"]
    assert "not by cutting sentences" in captured["prompt"]


def test_linkedin_compression_retries_before_fail_closed(monkeypatch):
    original = "منشور مطول " * 400
    compact = (
        "على الإدارة تحديد الوقائع والمستندات قبل اتخاذ القرار. "
        "ويجب تقييم الالتزامات والمسؤوليات والآثار القانونية والتشغيلية لكل بديل. "
        "كما ينبغي توثيق أسباب القرار ومراجعته قبل التنفيذ لتقليل احتمالات النزاع."
    )
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs["previous_context"])
        if len(calls) == 1:
            return {"post": "نص أطول " * 900}
        return {"post": compact}

    monkeypatch.setattr(run_main, "_diverse_generate_post", fake_generate)
    result = run_main._fit_linkedin_char_limit(
        original,
        api_key="test",
        model="test-model",
        topic="المساهمة الجنائية",
        legal_sources="",
    )
    assert result == compact
    assert len(calls) == 2
    assert "FINAL COMPRESSION PASS" in calls[1]


def test_live_wikimedia_provider_rejects_unrelated_map_before_download(monkeypatch, tmp_path):
    import image_generator

    calls = []

    class Response:
        ok = True
        headers = {"content-type": "application/json"}

        def json(self):
            return {
                "query": {
                    "pages": {
                        "1": {
                            "title": "File:Carte de la Basse-Egypte et du Fayoum.jpg",
                            "imageinfo": [{
                                "thumburl": "https://example.invalid/map.jpg",
                                "url": "https://example.invalid/map.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Map.jpg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "Public domain"},
                                    "ImageDescription": {"value": "Historical map of Lower Egypt and Fayoum."},
                                },
                            }],
                        }
                    }
                }
            }

    def fake_get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(image_generator.requests, "get", fake_get)
    try:
        image_generator.create_legal_image(
            topic="نزاع بشأن إجراءات العمل",
            image_brief="A contemporary open plan office bathed in natural light.",
            visual_description="A contemporary open plan office bathed in natural light.",
            post_context="A post about employment procedures.",
            output_path=str(tmp_path / "office.jpg"),
            aspect_ratio="9:16",
            provider="wikimedia",
        )
    except image_generator.ImageGenerationError as exc:
        assert "no downloadable image" in str(exc)
    else:
        raise AssertionError("An unrelated map must never be accepted as an office scene.")

    assert len(calls) == 1
    assert calls[0] == "https://commons.wikimedia.org/w/api.php"
