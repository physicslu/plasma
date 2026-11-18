# Independent AXI-SWD IP project; no composite MPE and no F1-B build driver.
# Host-only source. Actual Vivado synthesis/DRC/HWH/bitstream NOT_RUN.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
foreach key {PLASMA_SWD_BUILD PLASMA_BOARD_REPO} {
    if {![info exists ::env($key)] || $::env($key) eq ""} {
        error "SWD_PROJECT_REQUIRED_ENV_MISSING:$key"
    }
}
set build_dir [file normalize $::env(PLASMA_SWD_BUILD)]
set board_repo [file normalize $::env(PLASMA_BOARD_REPO)]
if {![file isdirectory $board_repo]} {
    error "SWD_BOARD_REPOSITORY_UNAVAILABLE"
}
file mkdir $build_dir
set_param board.repoPaths [list $board_repo]
set board_part tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board_part]] != 1} {
    error "SWD_PYNQ_Z2_BOARD_PART_NOT_PINNED_OR_AVAILABLE"
}
create_project z2_swd_independent [file join $build_dir project] \
    -part xc7z020clg400-1 -force
set_property board_part $board_part [current_project]
set sources [list \
    [file join $pl_dir rtl swd plasma_swd_transaction_engine.sv] \
    [file join $pl_dir rtl swd plasma_swd_site_axi_lite.sv]]
foreach p $sources {
    if {![file isfile $p]} {error "SWD_PROJECT_REQUIRED_RTL_MISSING:$p"}
}
add_files -norecurse $sources
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1] *.sv]
set xdc [file join $pl_dir constraints pynq-z2 z2-swd-independent.xdc]
if {![file isfile $xdc]} {error "SWD_PROJECT_XDC_MISSING"}
add_files -fileset constrs_1 -norecurse $xdc
source [file join $script_dir create_block_design.tcl]
puts "SWD_INDEPENDENT_AXI_PROJECT_SOURCE_READY_NO_BITSTREAM_OR_HIL"
