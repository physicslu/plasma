# One 64KiB GP0 aperture, not five legacy 4KiB apertures.
# No external PL IO; synthetic DPIDR never leaves internal wrapper nets.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {
    error "F1 Z2 50MHz board crystal mismatch"
}
set_property -dict [list CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps
set unified [create_bd_cell -type module -reference fixed_ppu_z2_internal_fixture_axi unified_0]
set_property CONFIG.PPU_BASE 0x40000000 $unified
if {[llength [get_bd_intf_pins -quiet unified_0/S_AXI]] != 1} {
    error "F1 S_AXI inference missing: no automatic loose pin wiring"
}
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins unified_0/S_AXI]
assign_bd_address -offset 0x40000000 -range 64K -target_address_space \
    [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs unified_0/S_AXI/reg0] -force

# The PS FCLK0 / synchronized reset must actually reach the module.
set clks [get_bd_nets -quiet -of_objects [get_bd_pins unified_0/s_axi_aclk]]
set rst [get_bd_nets -quiet -of_objects [get_bd_pins unified_0/s_axi_aresetn]]
if {[llength $clks] != 1 || [llength $rst] != 1} {
    error "F1 AXI clock/reset not connected"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $clks] [get_bd_pins ps7_0/FCLK_CLK0]] == -1} {
    error "F1 AXI clock not driven by FCLK0"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $rst] [get_bd_pins rst_ps7_0_100M/peripheral_aresetn]] == -1} {
    error "F1 AXI reset not synchronized"
}
set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 1} {error "F1 requires exactly one PS7 GP0 segment"}
set segment [lindex $segments 0]
if {![string match "*unified_0*" [get_property NAME $segment]] ||
    [get_property OFFSET $segment] != 0x40000000 ||
    [get_property RANGE $segment] != 65536} {
    error "F1 64KiB Unified AXI mapping mismatch"
}
foreach port [get_bd_ports -quiet *] {
    set name [get_property NAME $port]
    if {![string match "DDR_*" $name] && ![string match "FIXED_IO_*" $name]} {
        error "F1 external PL port prohibited: $name"
    }
}
validate_bd_design
save_bd_design
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "FIXED_F1_BD_SOURCE_READY_NO_HARDWARE"
