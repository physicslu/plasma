create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {error "PYNQ-Z2 PS crystal preset mismatch"}
set_property -dict [list CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps
set identity [create_bd_cell -type module -reference pl_identity_axi_lite identity_0]
set_property -dict [list CONFIG.CAPABILITY_FLAGS {0} CONFIG.STRICT_ADDRESS {1} \
    CONFIG.AXI_BASE_ADDRESS {0x40000000}] $identity
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} [get_bd_intf_pins identity_0/S_AXI]
# Minimum AXI peripheral aperture; the slave only accepts 8 aligned words.
assign_bd_address -offset 0x40000000 -range 4K -target_address_space \
    [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs identity_0/S_AXI/reg0] -force
set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 1} {error "Unexpected PS AXI address segments"}
set seg [lindex $segments 0]
set addr [get_property OFFSET $seg]
set range [get_property RANGE $seg]
if {$addr != 0x40000000 || $range != 4096} {error "Identity AXI aperture mismatch: $addr $range"}
# Only dedicated PS DDR/FIXED_IO interfaces may leave the design.
if {[llength [get_bd_ports -quiet *]] != 0} {error "External PL scalar ports are forbidden"}
validate_bd_design
save_bd_design
set fp [open [file join $generated_dir identity-axi-base.txt] w]
puts $fp [format "0x%08X" $addr]
close $fp
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "IDENTITY_ONLY_BD_PASS base=$addr range=$range"
