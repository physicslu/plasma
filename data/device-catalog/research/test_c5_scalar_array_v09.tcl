# Host-side Tcl semantics proof only. This does NOT source OpenOCD nor touch an MCU.
set dev_id_loader {}
set die_max_flash_size {
    0x44E 0x200
    0x44F 0x100
    0x45A 0x400
}
if {[array exists dev_id_loader] || [array exists die_max_flash_size]} {
    error "scalar set unexpectedly created an array"
}
set result [catch {info exists dev_id_loader(0x44E)} value]
if {$result == 0 && $value != 0} {
    error "original scalar loader array-index unexpectedly resolved"
}
set result [catch {info exists die_max_flash_size(0x44E)} value]
if {$result == 0 && $value != 0} {
    error "original scalar fallback array-index unexpectedly resolved"
}
unset dev_id_loader
unset die_max_flash_size
array set dev_id_loader {
    0x44E "local-immutable-loader-example.xldr"
}
array set die_max_flash_size {
    0x44E 0x200
    0x44F 0x100
    0x45A 0x400
}
if {![info exists dev_id_loader(0x44E)] ||
    ![info exists die_max_flash_size(0x44E)] ||
    $die_max_flash_size(0x44E) != 0x200} {
    error "the corrected Tcl array semantics did not work"
}
puts "TCL_SCALAR_ARRAY_MISMATCH_CONFIRMED (host-side only): PASS"
