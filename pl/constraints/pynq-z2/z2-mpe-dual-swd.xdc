# PLASMA MPE TWO INDEPENDENT SWD SITES (PYNQ-Z2 Zynq-7020).
# Source-only Gate 1 pin mapping; not a hardware admission or Image manifest.
#
# Site 1 (SV packed index 0) -> dedicated PMODA / JA for PLASMA:
#   JA pin 1 Y18 SWCLK, pin 2 Y19 SWDIO, GND pin 5/11.
#   Physical PCB caveat: JA I/O shares nets with Raspberry Pi 40-pin header.
#   Do not attach another active driver/HAT when PLASMA reserves JA.
# Site 2 (SV packed index 1) -> dedicated PMODB / JB:
#   JB pin 1 W14 SWCLK, pin 2 Y14 SWDIO, GND pin 5/11.
#
# Only two SWCLK and two SWDIO pins. All unused pins stay unbound/Hi-Z.
# No NRST, 5V, VPP, output power, pullups or timing exceptions here.
#
# All FPGA IO are 3.3V LVCMOS; never connect 1.8V or 5V SWD directly.
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {swclk_io[0]}]
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports {swdio_io[0]}]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {swclk_io[1]}]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {swdio_io[1]}]
