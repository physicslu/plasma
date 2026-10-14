# Read-only Vivado installation / Z2 board-preset preflight.
# No RTL synthesis, bitstream generation or FPGA/device access is performed.
set part xc7z020clg400-1
puts "PLASMA_VIVADO_VERSION [version -short]"
set parts [get_parts -quiet $part]
if {[llength $parts] != 1} {
    error "VIVADO_PREFLIGHT_FAIL: target part $part not installed"
}
if {![info exists ::env(PLASMA_BOARD_REPO)]} {
    error "VIVADO_PREFLIGHT_FAIL: PLASMA_BOARD_REPO must point to pinned Board Files"
}
set board_repo [file normalize $::env(PLASMA_BOARD_REPO)]
foreach required [list board.xml preset.xml part0_pins.xml] {
    if {![file isfile [file join $board_repo pynq-z2 A.0 $required]]} {
        error "VIVADO_PREFLIGHT_FAIL: missing $required in pinned PYNQ-Z2 board repository"
    }
}
set_param board.repoPaths [list $board_repo]
create_project -in_memory -part $part
set board "tul.com.tw:pynq-z2:part0:1.0"
set boards [get_board_parts -quiet $board]
puts "PLASMA_BOARD_CANDIDATES [join $boards ,]"
if {[llength $boards] != 1 || [lindex $boards 0] ne $board} {
    error "VIVADO_PREFLIGHT_FAIL: pinned PYNQ-Z2 board not available (found $boards)"
}
set_property board_part $board [current_project]
if {[get_property board_part [current_project]] ne $board} {
    error "VIVADO_PREFLIGHT_FAIL: board_part property cannot be assigned"
}
puts "PLASMA_VIVADO_TARGET_PART $part"
puts "PLASMA_VIVADO_BOARD_PART $board"
puts "PLASMA_VIVADO_PREFLIGHT_PASS"
close_project
