# Entry point for source-controlled FPGA project generation.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
set generated_dir [file join $pl_dir build z2-swd-gpio generated]
set project_dir [file join $pl_dir build z2-swd-gpio project]

foreach source [list \
    [file join $pl_dir rtl site swd_emio_bridge.sv] \
    [file join $pl_dir rtl bus pl_identity_axi_lite.sv] \
    [file join $pl_dir constraints pynq-z2 z2-swd-gpio.xdc] \
    [file join $generated_dir plasma_identity_generated.vh]] {
    if {![file isfile $source]} {error "Missing required PL source: $source"}
}

# Never depend on user-specific Vivado Board Store state. The build runner
# fetches the pinned upstream commit into ignored pl/build and exports its path.
if {![info exists ::env(PLASMA_BOARD_REPO)]} {
    error "PLASMA_BOARD_REPO is required; use build-on-swpc.sh"
}
set board_repo [file normalize $::env(PLASMA_BOARD_REPO)]
foreach required [list board.xml preset.xml part0_pins.xml] {
    if {![file isfile [file join $board_repo pynq-z2 A.0 $required]]} {
        error "Missing PYNQ-Z2 board repository file: $required"
    }
}
set_param board.repoPaths [list $board_repo]
set board "tul.com.tw:pynq-z2:part0:1.0"
set boards [get_board_parts -quiet $board]
if {[llength $boards] != 1 || [lindex $boards 0] ne $board} {
    error "Expected pinned PYNQ-Z2 board $board, Vivado detected: $boards"
}
create_project z2_swd_gpio $project_dir -part xc7z020clg400-1 -force
set_property board_part $board [current_project]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]

set sources [list \
    [file join $pl_dir rtl site swd_emio_bridge.sv] \
    [file join $pl_dir rtl bus pl_identity_axi_lite.sv]]
add_files -norecurse $sources
foreach source $sources {set_property file_type SystemVerilog [get_files $source]}
add_files -norecurse [file join $generated_dir plasma_identity_generated.vh]
set_property file_type {Verilog Header} [get_files [file join $generated_dir plasma_identity_generated.vh]]
set_property include_dirs [list $generated_dir] [get_filesets sources_1]
add_files -fileset constrs_1 -norecurse [file join $pl_dir constraints pynq-z2 z2-swd-gpio.xdc]
update_compile_order -fileset sources_1
source [file join $script_dir create_block_design.tcl]
puts "PROJECT_CREATED [file join $project_dir z2_swd_gpio.xpr]"
