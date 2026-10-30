"""Host-only source-graph contract for separately addressable SWD IPs.

Vivado Tcl inspection is a structural smoke guard, not Vivado elaboration,
implementation, HWH authenticity, Bitstream or physical HIL qualification.
"""
from pathlib import Path

PL = Path(__file__).resolve().parents[1]
PROJECT = PL / "projects/z2-swd-independent"


def test_vivado_uses_two_independent_axi_slaves_and_one_interconnect():
    t = (PROJECT / "create_block_design.tcl").read_text()
    assert "xilinx.com:ip:axi_interconnect:2.1" in t
    assert "CONFIG.NUM_MI {2}" in t
    assert t.count("-type module -reference plasma_swd_site_axi_lite") == 2
    assert "CONFIG.SITE_BASE_ADDRESS {0x43C01000}" in t
    assert "CONFIG.SITE_BASE_ADDRESS {0x43C02000}" in t
    assert "assign_bd_address -offset 0x43C01000 -range 4K" in t
    assert "assign_bd_address -offset 0x43C02000 -range 4K" in t
    assert "PS7_GP0_MUST_MAP_EXACTLY_TWO_SITE_SLAVES" in t
    assert "make_bd_pins_external" in t
    for sig in ("swclk_site1", "swdio_site1", "swclk_site2", "swdio_site2"):
        assert sig in t


def test_vivado_sources_standalone_new_swd_only_and_no_mpe_fallback():
    p = (PROJECT / "create_project.tcl").read_text()
    assert "rtl swd plasma_swd_transaction_engine.sv" in p
    assert "rtl swd plasma_swd_site_axi_lite.sv" in p
    assert "z2-swd-independent.xdc" in p
    for banned in ("plasma_mpe_", "fixed_ppu_", "z2-fixed-unified-site1",
                   "swd03_dpidr_responder", "swd_waveform_engine",
                   "bluepill_remote_bitbang"):
        assert banned not in p


def test_vivado_2026_1_readonly_reset_parameter_is_verified_not_written():
    bd = (PROJECT / "create_block_design.tcl").read_text()
    active = "\n".join(line for line in bd.splitlines()
                       if not line.lstrip().startswith("#"))
    # Real SWPC Vivado 2026.1 emits BD 41-737 CRITICAL WARNING when
    # CONFIG.C_EXT_RESET_HIGH is written. The default is 0 in real HWH;
    # retain fail-closed HWH validation of that actual output instead.
    assert "set_property CONFIG.C_EXT_RESET_HIGH" not in active
    verifier = (PROJECT / "verify_hwh.py").read_text()
    assert 'number(parameters(rst).get("C_EXT_RESET_HIGH")) == 0' in verifier
    assert 'ports(rst).get("ext_reset_in") == "ps7_0_FCLK_RESET0_N"' in verifier


def test_pin_contract_has_exactly_four_unique_board_pads():
    xdc = (PL / "constraints/pynq-z2/z2-swd-independent.xdc").read_text()
    actual = [x for x in xdc.splitlines() if x.startswith("set_property ")]
    assert actual == [
        "set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports swclk_site1]",
        "set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports swdio_site1]",
        "set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports swclk_site2]",
        "set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports swdio_site2]",
    ]


def test_build_is_host_only_does_not_auto_load_fpga():
    build = (PROJECT / "build_bitstream.tcl").read_text()
    for required in ("launch_runs synth_1", "launch_runs impl_1",
                     "report_timing_summary", "report_drc",
                     "report_methodology", "report_datasheet",
                     "report_io", "check_timing", "system.hwh",
                     "system_wrapper.bit", "SWD_NO_AUTOMATIC_DOWNLOAD"):
        assert required in build
    for banned in ("fpga_manager", "ssh ", "sudo ", "scp ", "open_hw_target",
                   "program_hw_devices", "z2-fixed-unified-site1",
                   "plasma_vivado_host_build"):
        assert banned not in build
    # The project-specific HWH verifier is an upcoming requirement.
    # Its addition must never make this independent-build guard fail.
    verifier = PROJECT / "verify_hwh.py"
    if verifier.exists():
        content = verifier.read_text()
        assert "swd_site1" in content and "swd_site2" in content


def test_only_off_normal_modes_and_no_debug_registers_or_pin_drivers():
    r = (PL / "rtl/swd/plasma_swd_site_axi_lite.sv").read_text()
    assert "parameter integer SITE_ID = 1" in r
    assert "SITE_BASE_ADDRESS" in r
    assert "plasma_swd_transaction_engine u_transaction" in r
    assert "mode_q == MODE_NORMAL" in r
    assert "MODE_OFF=2'd0, MODE_NORMAL=2'd1" in r
    assert "data_w[31:1] == 0" in r
    assert "32'h00050000 | SITE_ID" in r
    assert "8'h38:" in r  # OFF/NORMAL hardware guard retained
    for forbidden in ("MODE_DEBUG", "debug_pad", "debug_oe_q",
                      "debug_clk_q", "debug_out_q", "8'h3C:", "8'h40:",
                      "plasma_mpe_", "z2-swd03-axi", "swd_transaction_master",
                      "bluepill_remote_bitbang"):
        assert forbidden not in r, forbidden


def test_offchip_swd_timing_signoff_cannot_be_inferred_from_internal_wns():
    verifier = (PROJECT / "verify_hwh.py").read_text()
    wrapper = (PL.parent / "scripts/plasma_swd_host_build.py").read_text()
    assert 'external_swd_io_timing' in verifier
    assert 'external_io_timing_qualified": False' in verifier
    assert 'external_swd_io_timing' in wrapper
    assert "datasheet_io.rpt" in verifier
    assert "io_pad_configuration.rpt" in verifier
    xdc = (PL / "constraints/pynq-z2/z2-swd-independent.xdc").read_text()
    assert "set_false_path" not in xdc
    assert "set_clock_groups -asynchronous" not in xdc
    assert "set_input_delay 0" not in xdc
    assert "set_output_delay 0" not in xdc
    assert (PROJECT / "external-timing-audit.md").is_file()

def test_unqualified_fast_swd_frequency_is_denied_at_both_layers():
    site = (PL / "rtl/swd/plasma_swd_site_axi_lite.sv").read_text()
    engine = (PL / "rtl/swd/plasma_swd_transaction_engine.sv").read_text()
    # Candidate design maximum: 100 MHz / (2*4) = 12.5 MHz.
    # Do not conflate this RTL admission with any target's HIL-qualified max.
    assert "MIN_HALF_PERIOD = 16'd4" in site
    assert "MIN_HALF_PERIOD = 16'd4" in engine
    assert "data_w[15:0] >= MIN_HALF_PERIOD" in site
    assert "cmd_half_period < MIN_HALF_PERIOD" in engine
    assert "half_q <= 16'd500" in site  # 100 kHz reset default
    assert "12.5MHz" in site and "12.5MHz" in engine
    assert "DATA/OE" not in (PL / "constraints/pynq-z2/z2-swd-independent.xdc").read_text()
