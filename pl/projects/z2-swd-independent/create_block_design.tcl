# Source-only PYNQ-Z2 PS7 GP0 -> ordinary AXI interconnect -> TWO
# independently addressable SWD IP AXI4-Lite slaves. No PL MPE Manager.
# Do not claim this BD is valid HWH before actual Vivado implementation.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {
    error "SWD_Z2_PS7_CRYSTAL_MISMATCH"
}
set_property -dict [list \
    CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps

# An ordinary 1x2 AXI Interconnect only routes address/control accesses.
# It is NOT a shared SWD bit engine; the two Sites run concurrently in PL.
set fabric [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] $fabric
set site1 [create_bd_cell -type module -reference plasma_swd_site_axi_lite swd_site1]
set site2 [create_bd_cell -type module -reference plasma_swd_site_axi_lite swd_site2]
set_property -dict [list CONFIG.SITE_ID {1} CONFIG.SITE_BASE_ADDRESS {0x43C01000}] $site1
set_property -dict [list CONFIG.SITE_ID {2} CONFIG.SITE_BASE_ADDRESS {0x43C02000}] $site2
foreach cell {swd_site1 swd_site2} {
    if {[llength [get_bd_intf_pins -quiet $cell/S_AXI]] != 1} {
        error "SWD_AXILITE_SLAVE_INFERENCE_FAILED:$cell"
    }
}
connect_bd_intf_net [get_bd_intf_pins ps7_0/M_AXI_GP0] \
    [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
    [get_bd_intf_pins swd_site1/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M01_AXI] \
    [get_bd_intf_pins swd_site2/S_AXI]

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M]
set_property CONFIG.C_EXT_RESET_HIGH {0} $rst
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] \
    [get_bd_pins ps7_0/M_AXI_GP0_ACLK] \
    [get_bd_pins rst_ps7_0_100M/slowest_sync_clk] \
    [get_bd_pins axi_interconnect_0/ACLK] \
    [get_bd_pins axi_interconnect_0/S00_ACLK] \
    [get_bd_pins axi_interconnect_0/M00_ACLK] \
    [get_bd_pins axi_interconnect_0/M01_ACLK] \
    [get_bd_pins swd_site1/s_axi_aclk] \
    [get_bd_pins swd_site2/s_axi_aclk]
connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] \
    [get_bd_pins rst_ps7_0_100M/ext_reset_in]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] \
    [get_bd_pins axi_interconnect_0/ARESETN] \
    [get_bd_pins axi_interconnect_0/S00_ARESETN] \
    [get_bd_pins axi_interconnect_0/M00_ARESETN] \
    [get_bd_pins axi_interconnect_0/M01_ARESETN] \
    [get_bd_pins swd_site1/s_axi_aresetn] \
    [get_bd_pins swd_site2/s_axi_aresetn]

assign_bd_address -offset 0x43C01000 -range 4K \
    -target_address_space [get_bd_addr_spaces ps7_0/Data] \
    [get_bd_addr_segs swd_site1/S_AXI/reg0] -force
assign_bd_address -offset 0x43C02000 -range 4K \
    -target_address_space [get_bd_addr_spaces ps7_0/Data] \
    [get_bd_addr_segs swd_site2/S_AXI/reg0] -force

# Four *scalar* FPGA pad ports, physically independent JA/JB.
foreach {cell pin external} {
    swd_site1 swclk_io swclk_site1
    swd_site1 swdio_io swdio_site1
    swd_site2 swclk_io swclk_site2
    swd_site2 swdio_io swdio_site2
} {
    if {[llength [get_bd_pins -quiet $cell/$pin]] != 1} {
        error "SWD_BD_REQUIRED_PAD_MISSING:$cell/$pin"
    }
    make_bd_pins_external -name $external [get_bd_pins $cell/$pin]
}
# Site IRQ is not wired into PS7 in this first polling-only prototype.
# IRQ register semantics and Linux interrupts require separate qualification.

set regions [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $regions] != 2} {
    error "SWD_PS7_GP0_MUST_MAP_EXACTLY_TWO_SITE_SLAVES"
}
foreach {instance start} {swd_site1 0x43C01000 swd_site2 0x43C02000} {
    set mapped [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data] \
        -filter "NAME =~ *$instance*"]
    if {[llength $mapped] != 1 ||
        [get_property OFFSET $mapped] != $start ||
        [get_property RANGE $mapped] != 4096} {
        error "SWD_PS7_GP0_SITE_ADDRESS_MISMATCH:$instance"
    }
}
foreach pin [get_bd_ports -quiet *] {
    set name [get_property NAME $pin]
    if {![string match "DDR_*" $name] &&
        ![string match "FIXED_IO_*" $name] &&
        $name ni {swclk_site1 swdio_site1 swclk_site2 swdio_site2}} {
        error "SWD_UNEXPECTED_EXTERNAL_FPGA_PAD:$name"
    }
}
validate_bd_design
save_bd_design
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "SWD_TWO_INDEPENDENT_AXI_SLAVES_SOURCE_READY_NO_HIL"
