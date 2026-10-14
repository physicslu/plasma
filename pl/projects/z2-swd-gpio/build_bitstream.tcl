# Build source-controlled Z2 EMIO SWD PoC (NO hardware loading).
set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir create_project.tcl]

set jobs 4
if {[info exists ::env(PLASMA_VIVADO_JOBS)]} {
    set jobs $::env(PLASMA_VIVADO_JOBS)
}
if {![string is integer -strict $jobs] || $jobs < 1 || $jobs > 32} {
    error "PLASMA_VIVADO_JOBS must be 1..32"
}
set report_dir [file join $pl_dir build z2-swd-gpio reports]
file mkdir $report_dir

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1

set status [get_property STATUS [get_runs impl_1]]
if {![string match "write_bitstream Complete!*" $status]} {
    error "VIVADO_BUILD_FAILED: $status"
}
open_run impl_1
if {[llength [get_clocks]] == 0} {
    error "VIVADO_TIMING_FAILED: no implemented clocks"
}
report_timing_summary -file [file join $report_dir timing_summary.rpt]
report_drc -file [file join $report_dir drc.rpt]
report_utilization -file [file join $report_dir utilization.rpt]

# Do not accept successful bitstream output if the implemented AXI clock paths
# violate setup/hold timing. Limitations: unclocked PMOD GPIO electrical timing
# and real IC SWD are NOT qualified by this on-chip timing check.
set setup_paths [get_timing_paths -setup -max_paths 1]
set hold_paths [get_timing_paths -hold -max_paths 1]
if {[llength $setup_paths] == 0 || [llength $hold_paths] == 0} {
    error "VIVADO_TIMING_FAILED: no setup/hold timing paths"
}
set setup_slack [get_property SLACK [lindex $setup_paths 0]]
set hold_slack [get_property SLACK [lindex $hold_paths 0]]
if {$setup_slack < 0 || $hold_slack < 0} {
    error "VIVADO_TIMING_FAILED: setup=$setup_slack hold=$hold_slack"
}
puts "IMPLEMENTED_TIMING_PASS setup=$setup_slack hold=$hold_slack"
puts "VIVADO_VERSION [version -short]"
puts "BITSTREAM_BUILD_PASS"
