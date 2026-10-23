# Manual offline Vivado artifact candidate only. Not invoked by CI or hardware.
# A clean, dedicated worktree and pinned board repository are prerequisites.
set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir create_project.tcl]
set jobs 4
if {[info exists ::env(PLASMA_VIVADO_JOBS)]} {set jobs $::env(PLASMA_VIVADO_JOBS)}
if {![string is integer -strict $jobs] || $jobs < 1 || $jobs > 16} {
    error "PLASMA_VIVADO_JOBS must be in 1..16"
}
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {![string match "*Complete!*" [get_property STATUS [get_runs synth_1]]]} {
    error "BLUEPILL_Z2_SYNTHESIS_FAILED"
}
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {![string match "write_bitstream Complete!*" [get_property STATUS [get_runs impl_1]]]} {
    error "BLUEPILL_Z2_IMPLEMENTATION_FAILED"
}
open_run impl_1
set setup [get_timing_paths -setup -max_paths 1]
set hold [get_timing_paths -hold -max_paths 1]
if {[llength $setup] == 0 || [llength $hold] == 0 ||
        [get_property SLACK [lindex $setup 0]] < 0 ||
        [get_property SLACK [lindex $hold 0]] < 0} {
    error "BLUEPILL_Z2_TIMING_FAILED"
}
set report_dir [file join $pl_dir build z2-bluepill-rbb reports]
file mkdir $report_dir
report_timing_summary -file [file join $report_dir timing_summary.rpt]
report_drc -file [file join $report_dir drc.rpt]
report_utilization -file [file join $report_dir utilization.rpt]
puts "BLUEPILL_Z2_VIVADO_HOST_ARTIFACT_CANDIDATE_NOT_HIL"
