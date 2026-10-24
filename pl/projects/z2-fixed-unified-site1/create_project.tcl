# F1 SOURCE ONLY: PYNQ-Z2 XC7Z020 fixed-ABI unified Site1, no external PL IO.
# Never run from GitHub Actions or a Z2; a separate approval is required for Vivado.
set script_dir [file dirname [file normalize [info script]]]
set pl_dir [file normalize [file join $script_dir ../..]]
set build_dir $::env(PLASMA_F1_BUILD)
set board_repo $::env(PLASMA_BOARD_REPO)
set_param board.repoPaths [list $board_repo]
set board tul.com.tw:pynq-z2:part0:1.0
if {[llength [get_board_parts -quiet $board]] != 1} {
    error "F1 pinned PYNQ-Z2 board unavailable"
}
create_project z2_fixed_unified_site1 [file join $build_dir project] -part xc7z020clg400-1
set_property board_part $board [current_project]
add_files -norecurse [list \
    [file join $script_dir rtl fixed_ppu_z2_internal_fixture_axi.sv] \
    [file join $pl_dir rtl bus fixed_ppu_unified_axi_site1.sv] \
    [file join $pl_dir rtl bus fixed_fpga_ppu_global_identity_axi_lite.sv] \
    [file join $pl_dir rtl bus fixed_fpga_swd_site_axi_lite.sv] \
    [file join $pl_dir rtl site swd_transaction_master.sv] \
    [file join $pl_dir rtl site swd_waveform_engine.sv] \
    [file join $pl_dir rtl site swd03_dpidr_responder.sv]]
set_property file_type SystemVerilog [get_files *.sv]
source [file join $script_dir create_block_design.tcl]
