from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

CURRENT_GUIDANCE = (
    "README.md",
    "AGENTS.md",
    "software/README.md",
    "software/python/README.md",
    "software/python/docs/architecture.md",
    "software/python/docs/errors.md",
    "software/python/docs/protocol.md",
    "software/python/docs/test-guide.md",
    "software/web/README.md",
    "docs/architecture/domain-naming-migration.md",
    "docs/architecture/ppu-facility-sites.md",
    "docs/architecture/configuration-architecture.md",
    "docs/architecture/gateway-communication-recovery.md",
    "docs/architecture/manager-readonly-fleet-aggregation.md",
    "docs/deployment/README.md",
    "docs/deployment/web-runtime-hygiene.md",
    "docs/development/codex-cloud-environment.md",
    "docs/development/fpga-development-guide.md",
    "docs/development/fpga-verification-guide.md",
    "docs/development/local-ai-development-guide.md",
    "docs/development/multi-machine-development-guide.md",
    "docs/operator/plasma-console-guide.md",
    "docs/development/swpc-deployment.md",
    "docs/development/vscode-remote-workspace.md",
    "pl/AGENTS.md",
    "pl/README.md",
)

RETIRED_CURRENT_GUIDANCE_PHRASES = (
    "Plasma protocol v3.1 over TCP",
    "Plasma v3.1 TCP Server",
    "Plasma v3.1 TCP server",
    "Python HTTP REST Gateway",
    "Python REST Gateway",
    "Plasma Python Web Gateway",
    "Python Gateway API",
    "Plasma Web REST Gateway",
    "Plasma Programmer Console",
    "prototype currently enables CH0",
    "Prototype currently enables CH0",
    "CH0 / CH1",
    "CH0/CH1",
    "CH0、CH1",
)

CANONICAL_V33_GUIDANCE = (
    "README.md",
    "AGENTS.md",
    "software/README.md",
    "software/python/README.md",
    "software/python/docs/architecture.md",
    "software/python/docs/protocol.md",
    "software/python/docs/test-guide.md",
    "software/web/README.md",
    "docs/architecture/domain-naming-migration.md",
    "docs/architecture/ppu-facility-sites.md",
    "docs/architecture/configuration-architecture.md",
    "docs/architecture/gateway-communication-recovery.md",
    "docs/development/swpc-deployment.md",
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative_path", CURRENT_GUIDANCE)
def test_current_guidance_does_not_reintroduce_retired_runtime_vocabulary(
    relative_path: str,
) -> None:
    text = _read(relative_path)

    for legacy in RETIRED_CURRENT_GUIDANCE_PHRASES:
        assert legacy not in text, f"{relative_path} contains retired current-guidance text: {legacy}"


@pytest.mark.parametrize("relative_path", CANONICAL_V33_GUIDANCE)
def test_canonical_guidance_uses_current_protocol(relative_path: str) -> None:
    text = _read(relative_path)
    assert "v3.3" in text, f"{relative_path} must state the current v3.3 baseline"
    assert "v3.2" not in text, f"{relative_path} still presents retired v3.2 guidance"
    assert "PLASMA32" not in text, f"{relative_path} still presents retired PLASMA32 guidance"


@pytest.mark.parametrize(
    ("relative_path", "required"),
    (
        (
            "README.md",
            ("Facility", "PPU", "SITE 1", "Protocol v3.3", "Web REST API Contract v3", "Plasma Manager"),
        ),
        (
            "AGENTS.md",
            ("Facility", "PPU", "SITE 1", "Protocol v3.3", "Plasma Gateway", "Plasma Manager"),
        ),
        (
            "software/README.md",
            ("Facility", "PPU", "SITE 1", "Protocol v3.3", "Programming Asset", "plasma_manager"),
        ),
        (
            "software/python/README.md",
            ("PPU", "SITE 1", "v3.3", "Programming Asset", "Normalized Image", "plasma-manager"),
        ),
        (
            "software/python/docs/architecture.md",
            ("PPU", "SITE 1", "v3.3", "SiteManager", "Programming Asset", "Normalized Image"),
        ),
        (
            "software/python/docs/protocol.md",
            ("SITE 1", "site_id = 1", "PLASMA33", "Normalized Image"),
        ),
        (
            "software/python/docs/test-guide.md",
            ("SITE 1", "Protocol v3.3", "PLASMA33", "REST v3"),
        ),
        (
            "software/web/README.md",
            ("Plasma PPU Console", "SITE 1", "Protocol v3.3", "Programming Asset", "Plasma Gateway"),
        ),
        (
            "docs/architecture/ppu-facility-sites.md",
            ("Facility", "PPU", "SITE 1", "Protocol v3.3", "PLASMA33"),
        ),
        (
            "docs/architecture/manager-readonly-fleet-aggregation.md",
            ("Plasma Manager", "manager_required = false", "2-Site", "4-Site", "8-Site"),
        ),
        (
            "docs/development/swpc-deployment.md",
            ("Plasma PPU Programming Server", "Plasma Gateway", "v3.3", "Web REST API Contract v3"),
        ),
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


def test_canonical_gateway_terminology_separates_service_endpoint_and_linux_route() -> None:
    agents = _read("AGENTS.md")
    ppu_network = _read("docs/architecture/ppu-network-configuration.md")

    for phrase in (
        "Plasma Gateway",
        "Plasma Gateway API",
        "Plasma Gateway Endpoint",
        "Default Gateway",
    ):
        assert phrase in agents, f"AGENTS.md is missing canonical gateway terminology: {phrase}"

    assert "Default Gateway" in ppu_network
    assert "Plasma Gateway service" in ppu_network
    assert '"gateway"' in ppu_network


def test_canonical_architecture_examples_are_one_based() -> None:
    text = _read("docs/architecture/ppu-facility-sites.md")

    forbidden_examples = (
        "+-- Site 0",
        "+-- SITE 0",
        "- id: 0",
        '"site_id": 0',
        "?site=0",
    )
    for example in forbidden_examples:
        assert example not in text, f"canonical architecture contains zero-based example: {example}"


def test_historical_naming_document_is_not_a_compatibility_contract() -> None:
    text = _read("docs/architecture/multi-programmer-sites.md")

    assert "Historical" in text
    assert "Protocol v3.3" in text
    assert "not accepted by the current development runtime" in text
    assert "remains only as an explicit compatibility adapter" not in text
