# Recreate the btled project and build its bitstream.

set script_dir [file dirname [file normalize [info script]]]
source [file join $script_dir create_project.tcl]

set jobs 6
if {[info exists ::env(PLASMA_VIVADO_JOBS)]} {
    set jobs $::env(PLASMA_VIVADO_JOBS)
}

if {![string is integer -strict $jobs] || $jobs < 1} {
    error "PLASMA_VIVADO_JOBS must be a positive integer"
}

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1

set run_status [get_property STATUS [get_runs impl_1]]
if {![string match "write_bitstream Complete!*" $run_status]} {
    error "Bitstream build failed: $run_status"
}

puts "Bitstream build completed: [file join $project_dir btled.runs impl_1 btled.bit]"
