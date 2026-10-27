"""ADR-0005 host-only decision and negative-claim guard.

This guards an accepted *architecture direction*, not nonexistent RTL modes.
The composite MPE prototype must not masquerade as final SWD IP or a
version-qualified OpenOCD remote_bitbang SWD transport.
"""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs/adr/0005-independent-swd-ip-guarded-bitbang.md"
DOC = ROOT / "docs/architecture/plasma-mpe-dual-site-gate1.md"


def test_owner_selected_independent_swd_ip_and_no_mpe_manager():
    decision = ADR.read_text(encoding="utf-8")
    for required in (
        "Status: Accepted",
        "No MPE central Site Manager",
        "AXI Interconnect",
        "SWD IP Site 1",
        "SWD IP Site 2",
        "0x43C01000",
        "0x43C02000",
        "mutually exclusive",
        "no",
        "Path 2",
        "operator-cli",
        "VIVADO_BUILD_NOT_RUN",
        "PHYSICAL_HIL_NOT_RUN",
    ):
        assert required in decision, required


def test_opencd_012_is_explicitly_blocked_for_swd_remote_bitbang():
    decision = ADR.read_text(encoding="utf-8")
    assert "v0.12.0" in decision
    assert "jtag_only" in decision
    assert "lacks `swd_ops`" in decision
    assert "DEBUG_REMOTE_BITBANG_SWD=BLOCKED_VERSION_UNQUALIFIED" in decision
    assert "O/o" in decision and "d/e/f/g" in decision


def test_legacy_mpe_project_is_explicitly_nonproduction():
    historical = DOC.read_text(encoding="utf-8")
    assert "SUPERSEDED IMPLEMENTATION DIRECTION" in historical
    assert "not" in historical
    assert "new independent-IP topology" in historical
    assert "does not support SWD" in historical


@pytest.mark.parametrize("unsafe_claim", [
    "OPENOCD_012_SWDBB_SUPPORTED",
    "DEBUG_SWDBB_HIL_PASS",
    "MPE_FINAL_IMAGE_QUALIFIED",
    "BITBANG_AUTO_FALLBACK_ALLOWED",
])
def test_policy_rejects_known_false_qualification_claims(unsafe_claim):
    decision = ADR.read_text(encoding="utf-8")
    assert unsafe_claim not in decision
