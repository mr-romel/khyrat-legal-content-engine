"""Platform-neutral adapter contracts.

Adapters prepare payloads and capability information. They do not log in or
publish until an explicit, platform-supported integration is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PlatformCapabilities:
    platform: str
    can_discover: bool
    can_prepare: bool
    can_publish_automatically: bool
    requires_manual_approval: bool
    notes: str


class MarketplaceAdapter(Protocol):
    platform: str

    def capabilities(self) -> PlatformCapabilities: ...

    def prepare_service(self, draft: dict) -> dict: ...

    def prepare_offer(self, opportunity: dict) -> dict: ...


class KhamsatAdapter:
    platform = "khamsat"

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            "khamsat", False, True, False, True,
            "MVP prepares the service; publishing remains manual until an official supported integration is verified.",
        )

    def prepare_service(self, draft: dict) -> dict:
        return {"platform": self.platform, "action": "CREATE_SERVICE", "payload": draft}

    def prepare_offer(self, opportunity: dict) -> dict:
        raise ValueError("Khamsat uses service listings; offer preparation is not applicable.")


class MostaqlAdapter:
    platform = "mostaql"

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            "mostaql", False, True, False, True,
            "MVP prepares an offer for review; project discovery/submission integration is intentionally not automated yet.",
        )

    def prepare_service(self, draft: dict) -> dict:
        raise ValueError("Mostaql uses project offers; service preparation is not applicable.")

    def prepare_offer(self, opportunity: dict) -> dict:
        return {"platform": self.platform, "action": "SUBMIT_OFFER", "payload": opportunity}
