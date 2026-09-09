#!/usr/bin/env python3
"""STM32F7 thin adapter over the generic ST dual-surface browser transport."""

from __future__ import annotations

from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer


class STM32F7BrowserAcquirer(STDualSurfaceBrowserAcquirer):
    def __init__(self, *, base_by_url: dict[str, str], headless: bool = True) -> None:
        super().__init__(
            base_by_url=base_by_url,
            family_label="STM32F7",
            headless=headless,
        )
