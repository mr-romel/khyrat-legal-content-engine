"""Render entrypoint for the Marketplace dashboard.

Keeps the existing local dashboard untouched while adapting only the bind
address and port expected by Render's web-service runtime.
"""
from __future__ import annotations

import os

from marketplace import pro_dashboard

pro_dashboard.HOST = os.getenv("HOST", "0.0.0.0")
pro_dashboard.PORT = int(os.getenv("PORT", "8766"))

from marketplace.auto_dashboard import start


if __name__ == "__main__":
    start()
