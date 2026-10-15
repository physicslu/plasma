# Control/waveform loopback PYNQ-Z2 build. No EMIO or external PL I/O.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
set build_dir $::env(PLASMA_LOOPBACK_BUILD)
set generated_dir [file join $build_dir generated]
set board_repo $::env(PLASMA_BOARD_REPO)
set_param board.repoPaths [list $board_repo]
set board tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board]] != 1} {error "Pinned PYNQ-Z2 board not available"}
create_project z2_control_waveform [file join $build_dir project] -part xc7z020clg400-1
set_property board_part $board [current_project]
add_files -norecurse [list [file join $generated_dir pl_identity_axi_lite.sv] \
    [file join $pl_dir rtl bus pl_control_axi_lite.sv] \
    [file join $pl_dir rtl bus swd_command_axi_lite.sv] \
    [file join $pl_dir rtl site swd_waveform_engine.sv] \
    [file join $pl_dir rtl site pl_loopback_responder.sv]]
set_property file_type SystemVerilog [get_files *.sv]
source [file join $script_dir create_block_design.tcl]
