# Isolated source-only PYNQ-Z2 GP0 -> AXI GPIO -> PMODB candidate.
# Must be invoked from a reviewed, clean source checkout; NEVER loads FPGA.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
set build_dir [file join $pl_dir build z2-bluepill-rbb]
set generated_dir [file join $build_dir generated]
set project_dir [file join $build_dir project]
if {[file exists $project_dir]} {
    error "Refusing to overwrite existing Vivado project; use a clean worktree"
}
if {![info exists ::env(PLASMA_BOARD_REPO)]} {
    error "PLASMA_BOARD_REPO must identify the pinned, existing board repository"
}
set board_repo [file normalize $::env(PLASMA_BOARD_REPO)]
set expected_sha e02d6a3866b5465218f777168cdc51344ac94e07
if {[catch {exec git -C $board_repo rev-parse HEAD} found_sha] ||
        $found_sha ne $expected_sha} {
    error "PYNQ-Z2 board repository SHA mismatch"
}
foreach required {board.xml preset.xml part0_pins.xml} {
    if {![file isfile [file join $board_repo pynq-z2 A.0 $required]]} {
        error "Missing pinned PYNQ-Z2 board file: $required"
    }
}
foreach source [list     [file join $pl_dir rtl bus plasma_poc_swd_gpio_axi_lite.sv]     [file join $pl_dir rtl site plasma_poc_swd_pmod.sv]     [file join $pl_dir constraints pynq-z2 z2-bluepill-rbb.xdc]] {
    if {![file isfile $source]} {error "Missing candidate source: $source"}
}
set_param board.repoPaths [list $board_repo]
set board tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board]] != 1} {
    error "Pinned PYNQ-Z2 board part not found"
}
file mkdir $generated_dir
create_project z2_bluepill_rbb $project_dir -part xc7z020clg400-1
set_property board_part $board [current_project]
set_property target_language Verilog [current_project]
set sources [list     [file join $pl_dir rtl bus plasma_poc_swd_gpio_axi_lite.sv]     [file join $pl_dir rtl site plasma_poc_swd_pmod.sv]]
add_files -norecurse $sources
foreach src $sources {set_property file_type SystemVerilog [get_files $src]}
add_files -fileset constrs_1 -norecurse     [file join $pl_dir constraints pynq-z2 z2-bluepill-rbb.xdc]
update_compile_order -fileset sources_1
source [file join $script_dir create_block_design.tcl]
puts "BLUEPILL_Z2_SOURCE_PROJECT_CREATED_NOT_BUILT"
