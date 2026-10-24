# Owner-disconnected, single-Site PoC. Separate from fixed PPU image.
# Only one 4 KiB GP0 peripheral. No EMIO PS GPIO shortcut.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7     -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"}     [get_bd_cells ps7_0]
set crystal [get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps]
if {![string equal [format %.1f $crystal] "50.0"]} {
    error "PYNQ-Z2 board's 50 MHz PS preset is absent"
}
set_property -dict [list     CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0}     CONFIG.PCW_USE_M_AXI_GP0 {1}     CONFIG.PCW_M_AXI_GP0_FREQMHZ {100}     CONFIG.PCW_EN_CLK0_PORT {1}     CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps

set swd [create_bd_cell -type module -reference plasma_poc_swd_gpio_axi_lite swd_0]
set_property CONFIG.AXI_BASE_ADDRESS 0x40008000 $swd
set pads [create_bd_cell -type module -reference plasma_poc_swd_pmod pads_0]
if {[llength [get_bd_intf_pins -quiet swd_0/S_AXI]] != 1} {
    error "Blue Pill SWD AXI4-Lite inference missing"
}
apply_bd_automation -rule xilinx.com:bd_rule:axi4     -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"}     [get_bd_intf_pins swd_0/S_AXI]
# The AXI GP0 bus metadata must match the FCLK0-driven ACLK (100 MHz).
# Do not accept a stale board-preset GP0 10 MHz value after automation.
set gp0_freq [get_property CONFIG.PCW_M_AXI_GP0_FREQMHZ $ps]
if {![string equal [format %.1f $gp0_freq] "100.0"]} {
    error "BLUEPILL_Z2_GP0_CLOCK_METADATA_MISMATCH"
}
assign_bd_address -offset 0x40008000 -range 4K -target_address_space     [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs swd_0/S_AXI/reg0] -force

foreach signal {swclk swdio_out swdio_oe swdio_in} {
    connect_bd_net [get_bd_pins swd_0/$signal] [get_bd_pins pads_0/$signal]
}
create_bd_port -dir O swclk_io
create_bd_port -dir IO swdio_io
connect_bd_net [get_bd_ports swclk_io] [get_bd_pins pads_0/swclk_io]
connect_bd_net [get_bd_ports swdio_io] [get_bd_pins pads_0/swdio_io]

set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 1} {error "Exactly one GP0 aperture expected"}
set seg [lindex $segments 0]
if {![string match "*swd_0*" [get_property NAME $seg]] ||
        [get_property OFFSET $seg] != 0x40008000 ||
        [get_property RANGE $seg] != 4096} {
    error "Blue Pill SWD GP0 mapping and ABI decoder disagree"
}
set clocks [get_bd_nets -quiet -of_objects [get_bd_pins swd_0/s_axi_aclk]]
set resets [get_bd_nets -quiet -of_objects [get_bd_pins swd_0/s_axi_aresetn]]
if {[llength $clocks] != 1 || [llength $resets] != 1} {
    error "SWD AXI clock/reset not connected"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $clocks]         [get_bd_pins ps7_0/FCLK_CLK0]] == -1} {
    error "SWD AXI clock not sourced from PS7 FCLK0"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $resets]         [get_bd_pins rst_ps7_0_100M/peripheral_aresetn]] == -1} {
    error "SWD AXI reset is not PS7 synchronized peripheral_aresetn"
}
foreach p [get_bd_ports -quiet *] {
    set name [get_property NAME $p]
    if {![string match "DDR_*" $name] &&
        ![string match "FIXED_IO_*" $name] &&
        $name ni {swclk_io swdio_io}} {
        error "Unexpected external FPGA pin: $name"
    }
}
validate_bd_design
save_bd_design
set f [open [file join $generated_dir axi-address-map.txt] w]
puts $f "swd_0 0x40008000 4096"
close $f
set bd_file [get_files -quiet */system.bd]
if {[llength $bd_file] != 1} {error "Expected exactly one system.bd"}
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "BLUEPILL_Z2_BD_SOURCE_READY_NO_BIT_OR_HIL"
