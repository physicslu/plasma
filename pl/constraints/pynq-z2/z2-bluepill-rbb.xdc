# Candidate PYNQ-Z2 PMODB JB physical constraints, NOT electrical approval.
# Reuse only the existing board's named JB[0]/JB[1] pins; verify board revision.
# SWCLK = JB[0] W14, output-only. SWDIO = JB[1] Y14, bidirectional IOBUF.
# 3.3V LVCMOS only; NO 5V target, level shifter, VTref or target power here.
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports swclk_io]
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports swdio_io]
# NRST intentionally absent. No pullups, drive strength, timing exceptions.
