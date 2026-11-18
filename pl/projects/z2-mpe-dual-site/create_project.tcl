# PLASMA MPE: independent PYNQ-Z2 Vivado source project.
# Host-only; not an FPGA load, hardware qualification or a legacy F1-B project.
# Entry: build_bitstream.tcl via SHA-pinned Path 2 operator-cli Python.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
foreach key {PLASMA_MPE_BUILD PLASMA_BOARD_REPO} {
    if {![info exists ::env($key)] || $::env($key) eq ""} {
        error "MPE_REQUIRED_ENV_MISSING_$key"
    }
}
set build_dir [file normalize $::env(PLASMA_MPE_BUILD)]
set board_repo [file normalize $::env(PLASMA_BOARD_REPO)]
if {![file isdirectory $board_repo]} {
    error "MPE_BOARD_REPO_MISSING"
}
file mkdir $build_dir
set_param board.repoPaths [list $board_repo]
set board tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board]] != 1} {
    error "MPE_PINNED_Z2_BOARD_PART_UNAVAILABLE"
}
create_project z2_mpe_dual_site [file join $build_dir project] -part xc7z020clg400-1 -force
set_property board_part $board [current_project]
set rtl_sources [list \
    [file join $pl_dir rtl mpe plasma_mpe_swd_engine.sv] \
    [file join $pl_dir rtl mpe plasma_mpe_dual_swd_core.sv] \
    [file join $pl_dir rtl mpe plasma_mpe_swd_axi_lite.sv]]
foreach source $rtl_sources {
    if {![file isfile $source]} {error "MPE_RTL_SOURCE_MISSING:$source"}
}
add_files -norecurse $rtl_sources
set_property file_type SystemVerilog [get_files -of_objects [get_filesets sources_1] *.sv]
set xdc [file join $pl_dir constraints pynq-z2 z2-mpe-dual-swd.xdc]
if {![file isfile $xdc]} {error "MPE_BOARD_XDC_MISSING"}
add_files -fileset constrs_1 -norecurse $xdc
set_property used_in_synthesis true [get_files $xdc]
set_property used_in_implementation true [get_files $xdc]
source [file join $script_dir create_block_design.tcl]
puts "MPE_STANDALONE_Z2_PROJECT_GENERATED_NO_HARDWARE"
