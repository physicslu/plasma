# Three disjoint PS-visible AXI4-Lite apertures. No external PL pins.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {error "Board crystal preset mismatch"}
set_property -dict [list CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps
foreach {instance reference base} {
    identity_0 pl_identity_axi_lite 0x40000000
    control_0 pl_control_axi_lite 0x40001000
    swd_0 swd_command_axi_lite 0x40002000
} {
    set peripheral [create_bd_cell -type module -reference $reference $instance]
    set_property CONFIG.AXI_BASE_ADDRESS $base $peripheral
    if {$instance eq "identity_0"} {
        # Preserve Identity ABI v1; no physical SWD capability is advertised.
        set_property -dict [list CONFIG.CAPABILITY_FLAGS {0} CONFIG.STRICT_ADDRESS {1}] $peripheral
    }
    if {[llength [get_bd_intf_pins -quiet $instance/S_AXI]] != 1} {error "Missing inferred AXI interface: $instance"}
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
        -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} [get_bd_intf_pins $instance/S_AXI]
    assign_bd_address -offset $base -range 4K -target_address_space \
        [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs $instance/S_AXI/reg0] -force
}
set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 3} {error "Expected exactly three address segments"}
set fp [open [file join $generated_dir axi-address-map.txt] w]
foreach {instance base} {identity_0 0x40000000 control_0 0x40001000 swd_0 0x40002000} {
    set matches {}
    foreach segment $segments {
        if {[string match "*${instance}*" [get_property NAME $segment]]} {lappend matches $segment}
    }
    if {[llength $matches] != 1} {error "Ambiguous address segment: $instance"}
    set segment [lindex $matches 0]
    set offset [get_property OFFSET $segment]
    set size [get_property RANGE $segment]
    if {$offset != $base || $size != 4096} {error "Address map mismatch: $instance"}
    puts $fp "$instance [format 0x%08X $offset] $size"
}
close $fp
foreach port [get_bd_ports -quiet *] {
    set name [get_property NAME $port]
    if {![string match "DDR_*" $name] && ![string match "FIXED_IO_*" $name]} {error "External PL port forbidden: $name"}
}
validate_bd_design
save_bd_design
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "LOOPBACK_BD_PASS"
