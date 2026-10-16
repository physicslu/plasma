# Five independent 4 KiB apertures. No external SWD pins or PL IO.
# Original Identity / Control / SWD-00 behavior is preserved.
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7_0]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
if {[get_property CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ $ps] != 50} {
    error "Board crystal preset mismatch"
}
set_property -dict [list CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100}] $ps

foreach {instance reference base} {
    identity_0 pl_identity_axi_lite 0x40000000
    control_0 pl_control_axi_lite 0x40001000
    swd_0 swd_command_axi_lite 0x40002000
    transaction_0 swd_transaction_axi_lite 0x40003000
    lt02_0 pl_mmio_loopback_axi_lite 0x40004000
} {
    set peripheral [create_bd_cell -type module -reference $reference $instance]
    set_property CONFIG.AXI_BASE_ADDRESS $base $peripheral
    if {$instance eq "identity_0"} {
        # Identity claims no physical SWD capability.
        set_property -dict [list CONFIG.CAPABILITY_FLAGS {0} CONFIG.STRICT_ADDRESS {1}] $peripheral
    }
    if {[llength [get_bd_intf_pins -quiet $instance/S_AXI]] != 1} {
        error "Missing inferred AXI interface: $instance"
    }
    apply_bd_automation -rule xilinx.com:bd_rule:axi4 \
        -config {Master "/ps7_0/M_AXI_GP0" Clk "Auto"} [get_bd_intf_pins $instance/S_AXI]
    assign_bd_address -offset $base -range 4K -target_address_space \
        [get_bd_addr_spaces ps7_0/Data] [get_bd_addr_segs $instance/S_AXI/reg0] -force
}

# FPGA-synthesizable digital fixture, NOT physical target or emulated JTAG/SWD pins.
set fixture [create_bd_cell -type module -reference swd03_dpidr_responder fixture_0]
foreach {master_port fixture_port} {
    swclk swclk
    swdio_out host_out
    swdio_oe host_oe
} {
    connect_bd_net [get_bd_pins transaction_0/$master_port] \
        [get_bd_pins fixture_0/$fixture_port]
}
connect_bd_net [get_bd_pins fixture_0/swdio_in] \
    [get_bd_pins transaction_0/swdio_in]
connect_bd_net [get_bd_pins ps7_0/FCLK_CLK0] [get_bd_pins fixture_0/clk]
if {[llength [get_bd_pins -quiet rst_ps7_0_100M/peripheral_aresetn]] != 1} {
    error "Missing synchronized peripheral reset"
}
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] \
    [get_bd_pins fixture_0/rst_n]

set segments [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]]
if {[llength $segments] != 5} {error "Expected exactly five AXI address segments"}
set fp [open [file join $generated_dir axi-address-map.txt] w]
foreach {instance base} {
    identity_0 0x40000000
    control_0 0x40001000
    swd_0 0x40002000
    transaction_0 0x40003000
    lt02_0 0x40004000
} {
    set matches {}
    foreach segment $segments {
        if {[string match "*${instance}*" [get_property NAME $segment]]} {
            lappend matches $segment
        }
    }
    if {[llength $matches] != 1} {error "Ambiguous segment: $instance"}
    set segment [lindex $matches 0]
    set offset [get_property OFFSET $segment]
    set size [get_property RANGE $segment]
    if {$offset != $base || $size != 4096} {
        error "AXI address mismatch: $instance"
    }
    puts $fp "$instance [format 0x%08X $offset] $size"
}
close $fp

foreach port [get_bd_ports -quiet *] {
    set name [get_property NAME $port]
    if {![string match "DDR_*" $name] && ![string match "FIXED_IO_*" $name]} {
        error "External PL port forbidden: $name"
    }
}
validate_bd_design
save_bd_design
set bd_file [get_files */system.bd]
generate_target all $bd_file
add_files -norecurse [make_wrapper -files $bd_file -top]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "LT02_BD_PASS"
