"""Orbit/Flux entrypoint for the Marketplace dashboard.

Keeps the existing Marketplace server untouched while adapting its local-only
host/port defaults to Orbit's container runtime.
"""
from __future__ import annotations

import os

from marketplace import server

server.HOST = os.getenv("HOST", "0.0.0.0")
server.PORT = int(os.getenv("PORT", "8765"))

if __name__ == "__main__":
    server.main()
