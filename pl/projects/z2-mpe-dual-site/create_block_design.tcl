# New MPE Project PS7/AXI/JA+JB external-port integration (source only).
# This does not reuse the fixed F1-B internal-DPIDR fixture or build engine.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {
    error "MPE_Z2_CRYSTAL_MISMATCH"
}
set_property -dict [list \
    CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps
set mpe [create_bd_cell -type module -reference plasma_mpe_swd_axi_lite mpe_0]
if {[llength [get_bd_intf_pins -quiet mpe_0/S_AXI]] != 1} {
    error "MPE_AXI4LITE_INTERFACE_INFERENCE_FAILED"
}
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins mpe_0/S_AXI]
assign_bd_address -offset 0x43C00000 -range 64K -target_address_space \
    [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs mpe_0/S_AXI/reg0] -force

# Two vectorized physical SWD nets, four Pmod signal pins total.
# SWDIO is an inout IOBUF, not a shared or mirrored wire.
foreach {pin external} {swclk_io swclk_io swdio_io swdio_io} {
    set bdpin [get_bd_pins -quiet "mpe_0/$pin"]
    if {[llength $bdpin] != 1} {error "MPE_PHYSICAL_BD_PORT_NOT_FOUND_$pin"}
    make_bd_pins_external -name $external $bdpin
}
# IRQ remains a local status signal for this initial polling-only Build.
# Full interrupt wiring and RW1C ABI are separately gated; do NOT advertise it.
# Never export site_irq as an unconstrained physical FPGA pin.
set external_ports [get_bd_ports -quiet *]
foreach required {swclk_io swdio_io} {
    if {[llength [get_bd_ports -quiet $required]] != 1} {
        error "MPE_EXTERNAL_PORT_MISSING_$required"
    }
}
foreach port $external_ports {
    set name [get_property NAME $port]
    if {![string match "DDR_*" $name] &&
        ![string match "FIXED_IO_*" $name] &&
        $name ni {swclk_io swdio_io}} {
        error "MPE_UNEXPECTED_EXTERNAL_PL_PORT_$name"
    }
}
set clks [get_bd_nets -quiet -of_objects [get_bd_pins mpe_0/s_axi_aclk]]
set resets [get_bd_nets -quiet -of_objects [get_bd_pins mpe_0/s_axi_aresetn]]
if {[llength $clks] != 1 || [llength $resets] != 1} {
    error "MPE_PS7_AXI_CLOCK_RESET_UNCONNECTED"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $clks] [get_bd_pins ps7_0/FCLK_CLK0]] == -1} {
    error "MPE_PS7_FCLK0_NOT_CONNECTED"
}
if {[lsearch -exact [get_bd_pins -quiet -of_objects $resets] [get_bd_pins rst_ps7_0_100M/peripheral_aresetn]] == -1} {
    error "MPE_AXI_RESET_NOT_SYNCHRONIZED"
}
set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 1} {
    error "MPE_REQUIRES_EXACTLY_ONE_AXI_GP0_SEGMENT"
}
set seg [lindex $segments 0]
if {![string match "*mpe_0*" [get_property NAME $seg]] ||
    [get_property OFFSET $seg] != 0x43C00000 ||
    [get_property RANGE $seg] != 65536} {
    error "MPE_GP0_ADDRESS_DECODER_MISMATCH"
}
validate_bd_design
save_bd_design
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "MPE_Z2_PS7_AXI_JA_JB_BD_SOURCE_READY_NOT_DEPLOYED"
