# Isolated Tcl semantics fixture: NOT a vendor target cfg; no OpenOCD/device I/O.
# Values are immutable *source identifiers* only. No binaries loaded.
array set die_max_flash_size {
    0x44F 0x100
    0x44E 0x200
    0x45A 0x400
}
array set dev_id_loader {
    0x44F {Flash/STM32C5[34]x.xldr}
    0x44E {Flash/STM32C5[56]x.xldr}
    0x45A {Flash/STM32C5[9A]x.xldr}
}
foreach {id size path} {
    0x44F 0x100 {Flash/STM32C5[34]x.xldr}
    0x44E 0x200 {Flash/STM32C5[56]x.xldr}
    0x45A 0x400 {Flash/STM32C5[9A]x.xldr}
} {
    if {![info exists dev_id_loader($id)] || ![info exists die_max_flash_size($id)]} {
        error "missing host-only lookup group"
    }
    if {$die_max_flash_size($id) != $size || $dev_id_loader($id) ne $path} {
        error "synthetic host-only lookup mismatch"
    }
}
if {[array size dev_id_loader] != 3 || [array size die_max_flash_size] != 3 ||
    [info exists dev_id_loader(0x474)]} {
    error "synthetic host table unexpected/unknown groups"
}
puts "ST_C5_HOST_ARRAY_ONLY_PASS"
