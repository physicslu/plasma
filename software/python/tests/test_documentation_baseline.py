from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

CURRENT_GUIDANCE = (
    "README.md",
    "AGENTS.md",
    "software/README.md",
    "software/web/README.md",
    "docs/architecture/ppu-facility-sites.md",
    "docs/architecture/configuration-architecture.md",
    "docs/development/multi-machine-development-guide.md",
    "docs/development/swpc-deployment.md",
    "docs/development/local-ai-development-guide.md",
    "pl/README.md",
    "docs/development/fpga-development-guide.md",
    "docs/development/fpga-verification-guide.md",
)

LEGACY_CURRENT_GUIDANCE_PHRASES = (
    "CH0",
    "CH1",
    "Plasma protocol v3.1 over TCP",
    "Plasma v3.1 TCP Server",
    "Plasma v3.1 TCP server",
    "Python HTTP REST Gateway",
    "Python REST Gateway",
    "Plasma Python Web Gateway",
    "Python Gateway API",
    "Plasma Programmer Console",
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative_path", CURRENT_GUIDANCE)
def test_current_guidance_does_not_reintroduce_retired_runtime_vocabulary(
    relative_path: str,
) -> None:
    text = _read(relative_path)

    for legacy in LEGACY_CURRENT_GUIDANCE_PHRASES:
        assert legacy not in text, f"{relative_path} contains retired current-guidance text: {legacy}"


@pytest.mark.parametrize(
    ("relative_path", "required"),
    (
        ("README.md", ("Facility", "PPU", "SITE 1", "Protocol v3.2", "Plasma Web REST Gateway")),
        ("AGENTS.md", ("Facility", "PPU", "SITE 1", "Protocol v3.2", "Plasma Web REST Gateway")),
        ("software/README.md", ("Facility", "PPU", "SITE 1", "Protocol v3.2", "Plasma Web REST Gateway")),
        ("software/web/README.md", ("Plasma PPU Console", "SITE 1", "Protocol v3.2", "Plasma Web REST Gateway")),
        ("docs/architecture/ppu-facility-sites.md", ("Facility", "PPU", "SITE 1", "Protocol v3.2")),
        ("docs/development/swpc-deployment.md", ("Plasma PPU Programming Server", "Plasma Web REST Gateway", "v3.2")),
        ("pl/README.md", ("Programming Site", "rtl/site/")),
    ),
)
def test_current_guidance_states_the_canonical_baseline(
    relative_path: str,
    required: tuple[str, ...],
) -> None:
    text = _read(relative_path)

    for phrase in required:
        assert phrase in text, f"{relative_path} is missing canonical baseline text: {phrase}"


def test_canonical_architecture_examples_are_one_based() -> None:
    text = _read("docs/architecture/ppu-facility-sites.md")

    forbidden_examples = (
        "+-- Site 0",
        "+-- SITE 0",
        "- id: 0",
        '"site_id": 0',
        "?site=0",
        '"site_id": 0',
    )
    for example in forbidden_examples:
        assert example not in text, f"canonical architecture contains zero-based example: {example}"


def test_legacy_naming_document_describes_translation_not_identity_equivalence() -> None:
    text = _read("docs/architecture/multi-programmer-sites.md")

    assert "v3.1 channel_id 0 -> canonical / v3.2 site_id 1" in text
    assert "Do not interpret legacy `channel_id` as numerically identical to `site_id`" in text
