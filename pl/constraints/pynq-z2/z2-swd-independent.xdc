# New direct-addressed independent SWD IP project: PYNQ-Z2 XC7Z020.
# Site 1 = JA (SWCLK Y18, SWDIO Y19).
# Site 2 = JB (SWCLK W14, SWDIO Y14).
# These are FOUR distinct I/O ports from TWO independent AXI SWD IPs.
# Never drive power/NRST/VPP; valid 3.3V SWD and common GND only.
# Pmod JA shares PCB traces with Raspberry Pi header; no conflicting drivers.
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports swclk_site1]
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports swdio_site1]
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports swclk_site2]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports swdio_site2]
