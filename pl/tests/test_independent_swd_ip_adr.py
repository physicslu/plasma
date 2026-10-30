"""Host-only owner decision guard: final SWD IP is NORMAL-only.

ADR-0005 remains historical; ADR-0006 supersedes its SWD-specific Debug.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "docs/adr/0005-independent-swd-ip-guarded-bitbang.md"
NEW = ROOT / "docs/adr/0006-independent-swd-engine-and-future-gpio-bus.md"
SOURCE = ROOT / "pl/rtl/swd/plasma_swd_site_axi_lite.sv"
DOC = ROOT / "docs/architecture/plasma-mpe-dual-site-gate1.md"


def test_adopted_independent_swd_and_future_gpio_without_mpe_manager():
    a = NEW.read_text(encoding="utf-8")
    for word in ("Status: Accepted", "Supersedes ADR-0005", "AXI Interconnect",
                 "0x43C01000", "0x43C02000", "OFF=0", "NORMAL=1",
                 "0x00050001/0x00050002", "GPIO Bus", "I²C",
                 "JTAG", "SPI", "UART", "Gate 1",
                 "no hardware access", "no merge"):
        assert word.lower() in a.lower(), word
    assert "Status: Superseded" in OLD.read_text(encoding="utf-8")


def test_removed_swd_debug_is_impossible_via_rtl_or_host_controller():
    rtl = SOURCE.read_text(encoding="utf-8")
    driver = (ROOT / "software/python/plasma_interfaces/swd_site.py").read_text()
    assert "data_w[31:1] == 0" in rtl
    assert "32'h00050000 | SITE_ID" in rtl
    assert "0x00050000 | self.site_id" in driver
    for forbidden in ("MODE_DEBUG", "debug_pad", "debug_oe_q",
                      "debug_clk_q", "debug_out_q", "8'h3C:", "8'h40:"):
        assert forbidden not in rtl, forbidden
    for forbidden in ("DEBUG_DRIVE =", "DEBUG_SAMPLE ="):
        assert forbidden not in driver, forbidden
    for name in ("swd_debug_bitbang.py", "swd_debug_socket.py"):
        assert not (ROOT / "software/python/plasma_interfaces" / name).exists()
    for name in ("test_swd_debug_bitbang_host.py", "test_swd_debug_socket_host.py"):
        assert not (ROOT / "software/python/tests" / name).exists()


def test_historical_composite_mpe_remains_nonproduction():
    historical = DOC.read_text(encoding="utf-8")
    assert "SUPERSEDED IMPLEMENTATION DIRECTION" in historical
    assert "new independent-IP topology" in historical
    assert "does not support SWD" in historical
