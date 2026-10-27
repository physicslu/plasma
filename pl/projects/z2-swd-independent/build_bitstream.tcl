# Source-controlled, independent Site1+Site2 SWD IP Vivado build.
# Invoke ONLY via an owner-approved, SHA-pinned Path 2 operator-cli Python
# entrypoint on SWPC. This Tcl does not access PS/Z2/DUT/FPGA Manager.
# Gate 1 candidate: no real Vivado execution or timing PASS is claimed.
set script_dir [file dirname [file normalize [info script]]]
if {![info exists ::env(PLASMA_SWD_BUILD)] || $::env(PLASMA_SWD_BUILD) eq ""} {
    error "SWD_REQUIRED_OUTPUT_DIRECTORY_MISSING"
}
set build_dir [file normalize $::env(PLASMA_SWD_BUILD)]
set jobs 4
if {[info exists ::env(PLASMA_SWD_JOBS)]} {
    set jobs $::env(PLASMA_SWD_JOBS)
}
if {![string is integer -strict $jobs] || $jobs < 1 || $jobs > 16} {
    error "SWD_VIVADO_JOBS_OUT_OF_RANGE"
}
source [file join $script_dir create_project.tcl]
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {![string match "*Complete!*" [get_property STATUS [get_runs synth_1]]]} {
    error "SWD_VIVADO_SYNTHESIS_FAILED"
}
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {![string match "write_bitstream Complete!*" [get_property STATUS [get_runs impl_1]]]} {
    error "SWD_VIVADO_IMPLEMENTATION_FAILED"
}
open_run impl_1
set reports [file join $build_dir reports]
file mkdir $reports
report_timing_summary -file [file join $reports timing_summary.rpt]
# Routed die/package I/O electrical and interface path details. These reports
# provide real FPGA-side evidence; the off-board target/cable envelope still
# needs a separately verified source-controlled timing profile.
report_datasheet -sort_by port -show_all_corners -show_oe_timing -file [file join $reports datasheet_io.rpt]
report_io -file [file join $reports io_pad_configuration.rpt]
report_drc -file [file join $reports drc.rpt]
report_methodology -file [file join $reports methodology.rpt]
report_utilization -file [file join $reports utilization.rpt]
check_timing -verbose -file [file join $reports check_timing.rpt]
set setup [get_timing_paths -setup -max_paths 1]
set hold [get_timing_paths -hold -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1} {
    error "SWD_IMPLEMENTATION_TIMING_PATHS_MISSING"
}
set setup_slack [get_property SLACK [lindex $setup 0]]
set hold_slack [get_property SLACK [lindex $hold 0]]
if {$setup_slack < 0 || $hold_slack < 0} {
    error "SWD_IMPLEMENTATION_TIMING_NOT_MET"
}
foreach violation [get_drc_violations -quiet] {
    if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {
        error "SWD_IMPLEMENTATION_BLOCKING_DRC"
    }
}
set bitfiles [glob -nocomplain -types f \
    [file join $build_dir project z2_swd_independent.runs impl_1 *.bit]]
set hwhfiles [glob -nocomplain -types f \
    [file join $build_dir project z2_swd_independent.gen sources_1 bd system hw_handoff *.hwh]]
if {[llength $bitfiles] != 1 || [llength $hwhfiles] != 1} {
    error "SWD_BIT_HWH_ARTIFACT_MISSING_OR_AMBIGUOUS"
}
set artifact_dir [file join $build_dir artifacts]
file mkdir $artifact_dir
file copy -force [lindex $bitfiles 0] [file join $artifact_dir system_wrapper.bit]
file copy -force [lindex $hwhfiles 0] [file join $artifact_dir system.hwh]
# No blocking Methodology findings. Never waive design violations to force PASS.
set blocking_methodology {}
foreach issue [get_methodology_violations -quiet] {
    if {[get_property SEVERITY $issue] in {Error {Critical Warning}}} {
        lappend blocking_methodology $issue
    }
}
if {[llength $blocking_methodology] > 0} {
    error "SWD_IMPLEMENTATION_BLOCKING_METHODOLOGY"
}
# Report 'check_timing' explicitly; any timing category with violations must
# be reviewed. This source has not been validated by actual Vivado yet.
puts "SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS setup=$setup_slack hold=$hold_slack"
puts "SWD_HOST_BUILD_SOURCE_ONLY_REVIEW_REQUIRED setup=$setup_slack hold=$hold_slack"
puts "SWD_NO_AUTOMATIC_DOWNLOAD_OR_DUT_OPERATION"
