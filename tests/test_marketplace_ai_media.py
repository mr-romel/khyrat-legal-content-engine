from __future__ import annotations

import io

from PIL import Image

from marketplace.ai_media import KHAMSAT_SIZE, offer_terms, normalize_offer_price


def test_offer_price_is_five_dollar_increment():
    assert normalize_offer_price(5) == 5
    assert normalize_offer_price(9) == 5
    assert normalize_offer_price(14) == 10
    assert normalize_offer_price(25) == 25


def test_offer_budget_caps_price_and_keeps_multiple_of_five():
    price, days = offer_terms({
        "description": "ميزانية المشروع 20 دولار",
        "suggested_price_usd": 37,
        "suggested_days": 4,
    })
    assert price == 20
    assert price % 5 == 0
    assert days == 4


def test_offer_budget_dollar_suffix_is_detected():
    price, _ = offer_terms({
        "description": "Budget: 15$",
        "suggested_price_usd": 30,
    })
    assert price == 15


def test_khamsat_target_size_is_exact():
    assert KHAMSAT_SIZE == (1700, 970)
    buffer = io.BytesIO()
    Image.new("RGB", KHAMSAT_SIZE, "white").save(buffer, format="JPEG")
    assert Image.open(io.BytesIO(buffer.getvalue())).size == KHAMSAT_SIZE
