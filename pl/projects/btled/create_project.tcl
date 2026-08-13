# Recreate the btled Vivado project from version-controlled sources.

set script_dir  [file dirname [file normalize [info script]]]
set pl_dir      [file normalize [file join $script_dir ../..]]
set project_dir [file join $pl_dir build btled]
set rtl_file    [file join $pl_dir rtl examples btled.sv]
set xdc_file    [file join $pl_dir constraints pynq-z2 btled.xdc]

foreach required_file [list $rtl_file $xdc_file] {
    if {![file exists $required_file]} {
        error "Required source file not found: $required_file"
    }
}

file mkdir [file dirname $project_dir]
create_project btled $project_dir -part xc7z020clg400-1 -force

set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]

add_files -norecurse $rtl_file
set_property file_type SystemVerilog [get_files $rtl_file]
add_files -fileset constrs_1 -norecurse $xdc_file

set_property top btled [current_fileset]
update_compile_order -fileset sources_1

puts "Created Vivado project: [file join $project_dir btled.xpr]"
