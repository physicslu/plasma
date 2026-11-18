"""Canonical CLI PPU/Site selection; topology is verified against Manager Fleet."""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence

_SITE_TOKEN = re.compile(r"[0-9]+\Z")


@dataclass(frozen=True)
class Target:
    ppu_alias: str
    site_ids: tuple[int, ...]


def parse_targets(values: Sequence[str]) -> tuple[Target, ...]:
    """One entry per PPU, one-based sites, no physical-site-count assumptions."""
    result: list[Target] = []
    seen_ppus: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("target must be a string")
        alias, separator, site_text = value.partition(":")
        if (
            not separator or ":" in site_text or not alias or len(alias) > 96
            or alias != alias.strip() or any(ch.isspace() for ch in alias)
        ):
            raise ValueError("target must be PPU_ALIAS:SITE[,SITE...]")
        if alias in seen_ppus:
            raise ValueError(f"duplicate PPU alias: {alias}")
        tokens = site_text.split(",")
        if any(not _SITE_TOKEN.fullmatch(token) for token in tokens):
            raise ValueError(f"invalid Site list for PPU {alias}")
        sites = tuple(int(token) for token in tokens)
        if any(site < 1 for site in sites) or len(set(sites)) != len(sites):
            raise ValueError(f"Site IDs must be unique positive integers for {alias}")
        result.append(Target(alias, sites))
        seen_ppus.add(alias)
    return tuple(result)
