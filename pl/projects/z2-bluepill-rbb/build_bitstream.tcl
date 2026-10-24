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
report_methodology -file [file join $report_dir methodology.rpt]
check_timing -verbose -file [file join $report_dir check_timing.rpt]
report_utilization -file [file join $report_dir utilization.rpt]
# A report file is not DRC acceptance: fail before artifact emission when
# any implementation DRC error or critical warning remains.
foreach violation [get_drc_violations -quiet] {
    if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {
        error "BLUEPILL_Z2_BLOCKING_DRC: $violation"
    }
}

# The output is NEVER considered acceptable unless the implemented BIT and
# exported HWH BOTH exist and the hardware handoff matches our exact PS7,
# GP0 and external SWD topology. This stage does not open hardware.
set bit_path [file join $project_dir z2_bluepill_rbb.runs impl_1 system_wrapper.bit]
set hwh_path [file join $project_dir z2_bluepill_rbb.gen sources_1 bd system hw_handoff system.hwh]
if {![file isfile $bit_path] || ![file isfile $hwh_path]} {
    error "BLUEPILL_Z2_BIT_HWH_MISSING"
}
if {[catch {exec python3 [file join $script_dir verify_hwh.py] \
    --hwh $hwh_path --bit $bit_path} inspection]} {
    error "BLUEPILL_Z2_HWH_INSPECTION_FAILED: $inspection"
}
set receipt [file join $generated_dir artifact-inspection.json]
if {[file exists $receipt]} {
    error "BLUEPILL_Z2_RECEIPT_ALREADY_EXISTS"
}
set fd [open $receipt {WRONLY CREAT EXCL}]
puts $fd $inspection
close $fd
puts "BLUEPILL_Z2_BIT_HWH_INSPECTION_PASS_OFFLINE_NOT_HIL"
puts "BLUEPILL_Z2_VIVADO_HOST_ARTIFACT_CANDIDATE_NOT_HIL"
