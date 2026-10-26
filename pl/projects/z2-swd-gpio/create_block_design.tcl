# RETIRED: historical Tcl retained for offline code/tests only.
error "RETIRED_Z2_SWD_GPIO: retired FPGA image build entrypoint"
# Recreate the Z2 PS EMIO GPIO + AXI-Lite identity block design.
# Caller must create the project, add RTL, set the PYNQ-Z2 BOARD_PART and
# include pl/build/z2-swd-gpio/generated before sourcing this file.
create_bd_design system

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
# IMPORTANT: Vivado's default PS is NOT safe as a PYNQ-Z2 board configuration.
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
    [get_bd_cells ps7_0]

# Fail closed if the board preset was not applied; Z2 board reference uses 50MHz.
set crystal [get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps]
if {![string equal [format %.1f $crystal] "50.0"]} {
    error "PYNQ-Z2 50MHz PS clock preset missing (found $crystal MHz); refusing unsafe bitstream"
}

set_property -dict [list \
    CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {1} \
    CONFIG.PCW_GPIO_EMIO_GPIO_IO {64} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
] $ps

set gpio [create_bd_cell -type module -reference swd_emio_bridge swd_emio_0]
foreach signal {GPIO_O GPIO_T GPIO_I} {
    switch $signal {
        GPIO_O {set bridge gpio_o}
        GPIO_T {set bridge gpio_t}
        GPIO_I {set bridge gpio_i}
    }
    connect_bd_net [get_bd_pins ps7_0/$signal] [get_bd_pins swd_emio_0/$bridge]
}
foreach signal {swclk_io swdio_io nrst_io} {
    create_bd_port -dir IO $signal
    connect_bd_net [get_bd_ports $signal] [get_bd_pins swd_emio_0/$signal]
}

set identity [create_bd_cell -type module -reference pl_identity_axi_lite identity_0]
if {[llength [get_bd_intf_pins -quiet identity_0/S_AXI]] != 1} {
    error "Identity RTL AXI4-Lite interface was not inferred by Vivado"
}
apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
    -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} \
    [get_bd_intf_pins identity_0/S_AXI]

assign_bd_address
validate_bd_design
save_bd_design

# AXI base address is build output, not invented software constant.
set address_file [file join $generated_dir identity-axi-base.txt]
set found {}
foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]] {
    if {[string match "*identity_0*" [get_property NAME $seg]]} {
        lappend found [get_property OFFSET $seg]
    }
}
if {[llength $found] != 1} {
    error "Expected exactly one PS-visible identity AXI segment, got: $found"
}
set fp [open $address_file w]
puts $fp [format "0x%08X" [expr {[lindex $found 0]}]]
close $fp

set bd_file [get_files -quiet */system.bd]
if {[llength $bd_file] != 1} {
    error "Expected one generated system.bd"
}
generate_target all $bd_file
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "IDENTITY_BASE [lindex $found 0]"
puts "BLOCK_DESIGN_VALIDATED"
