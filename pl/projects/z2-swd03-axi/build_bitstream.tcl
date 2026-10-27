# RETIRED: historical Tcl retained for offline code/tests only.
error "RETIRED_Z2_SWD03_AXI: retired FPGA image build entrypoint"
# New SWD-03 host-only implementation; never programs the Z2.
set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir create_project.tcl]
set jobs $::env(PLASMA_VIVADO_JOBS)
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {![string match "*Complete!*" [get_property STATUS [get_runs synth_1]]]} {
    error "SWD-03 synthesis failed"
}
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {![string match "write_bitstream Complete!*" [get_property STATUS [get_runs impl_1]]]} {
    error "SWD-03 implementation failed"
}
open_run impl_1
set reports [file join $build_dir reports]
file mkdir $reports
report_timing_summary -file [file join $reports timing_summary.rpt]
report_drc -file [file join $reports drc.rpt]
report_methodology -file [file join $reports methodology.rpt]
report_utilization -file [file join $reports utilization.rpt]
check_timing -verbose -file [file join $reports check_timing.rpt]
set setup [get_timing_paths -setup -max_paths 1]
set hold [get_timing_paths -hold -max_paths 1]
if {[llength $setup] == 0 || [llength $hold] == 0} {
    error "SWD-03 missing timing paths"
}
set setup_slack [get_property SLACK [lindex $setup 0]]
set hold_slack [get_property SLACK [lindex $hold 0]]
if {$setup_slack < 0 || $hold_slack < 0} {
    error "SWD-03 implemented timing failed"
}
foreach violation [get_drc_violations -quiet] {
    if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {
        error "Blocking SWD-03 DRC: $violation"
    }
}
puts "SWD03_IMPLEMENTED_TIMING_PASS setup=$setup_slack hold=$hold_slack"
puts "SWD03_BITSTREAM_BUILD_PASS"
