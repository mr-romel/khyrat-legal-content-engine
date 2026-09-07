"""Pricing policy for Mostaql Marketplace offers.

Prices are intentionally USD-only and constrained to $5 multiples. No FX rate
or EGP conversion is used here; the operator chooses a platform price tier.
"""
from __future__ import annotations

from numbers import Real

MIN_PRICE_USD = 5
PRICE_STEP_USD = 5
MAX_PRICE_USD = 100


def validate_price_usd(value: Real) -> int:
    """Validate and normalize a Mostaql price to an integer USD amount."""
    price = float(value)
    if not price.is_integer():
        raise ValueError("سعر مستقل يجب أن يكون رقمًا صحيحًا بالدولار")
    price = int(price)
    if price < MIN_PRICE_USD or price % PRICE_STEP_USD:
        raise ValueError("سعر مستقل يجب أن يكون 5$ أو أحد مضاعفاتها")
    if price > MAX_PRICE_USD:
        raise ValueError(f"سعر مستقل لا يتجاوز ${MAX_PRICE_USD} في هذه النسخة")
    return price


def suggest_price_usd(score: int | float) -> int:
    """Choose a conservative $5-tier price from the acquisition score."""
    score = max(0.0, min(100.0, float(score)))
    if score >= 90:
        return 20
    if score >= 75:
        return 15
    if score >= 55:
        return 10
    return 5
