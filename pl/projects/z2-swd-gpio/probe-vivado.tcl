# Read-only Vivado installation / Z2 board-preset preflight.
# No RTL synthesis, bitstream generation or FPGA/device access is performed.
set part xc7z020clg400-1
puts "PLASMA_VIVADO_VERSION [version -short]"
set parts [get_parts -quiet $part]
if {[llength $parts] != 1} {
    error "VIVADO_PREFLIGHT_FAIL: target part $part not installed"
}
create_project -in_memory -part $part
set boards [get_board_parts -quiet *pynq-z2*]
puts "PLASMA_BOARD_CANDIDATES [join $boards ,]"
if {[llength $boards] != 1} {
    error "VIVADO_PREFLIGHT_FAIL: expected one registered PYNQ-Z2 board part; found [llength $boards]"
}
set board [lindex $boards 0]
if {![string match "tul.com.tw:pynq-z2:part0:*" $board]} {
    error "VIVADO_PREFLIGHT_FAIL: unexpected board identifier $board"
}
set_property board_part $board [current_project]
if {[get_property board_part [current_project]] ne $board} {
    error "VIVADO_PREFLIGHT_FAIL: board_part property cannot be assigned"
}
puts "PLASMA_VIVADO_TARGET_PART $part"
puts "PLASMA_VIVADO_BOARD_PART $board"
puts "PLASMA_VIVADO_PREFLIGHT_PASS"
close_project
