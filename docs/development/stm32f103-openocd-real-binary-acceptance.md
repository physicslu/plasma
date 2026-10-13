# STM32F103 Real OpenOCD Binary Software Acceptance

Status: **Reference software-only acceptance; no hardware initialization**

## Purpose

This acceptance closes the gap between the STM32F103 manufacturer-derived
programmer research and an actual Plasma-owned OpenOCD executable.

The validated chain is:

```text
ST manufacturer evidence
  -> frozen STM32F103C8T6 baseline
  -> Programming Profile / Execution IR
  -> generated STM32F103 reference programmer
  -> semantic differential against pinned OpenOCD source
  -> real pinned OpenOCD 0.12.0 binary
  -> real OpenOCD Tcl parser
  -> real target/stm32f1x.cfg
  -> real stm32f1x Flash-bank registration
```

This is deliberately not a Flash transaction or HIL test.

## Exact-device geometry

The exact target remains `STM32F103C8T6`.

Manufacturer authority fixes Main Flash at:

```text
base: 0x08000000
size: 64 KiB
```

The acceptance passes that exact 64-KiB value into the real upstream
`target/stm32f1x.cfg` through its documented `FLASH_SIZE` override before the
target script is parsed.

The real OpenOCD process must then report one Flash bank with:

```text
name:   stm32f1x.flash
driver: stm32f1x
base:   0x08000000
size:   65536
target: stm32f1x.cpu
```

A 128-KiB result fails closed. The Blue Pill board configuration is never
loaded and cannot be used as exact-ICPN authority.

## Why noinit is mandatory

OpenOCD normally performs automatic `init` after configuration parsing.
`init` performs adapter initialization, transport initialization, DAP
initialization and target examination.

This acceptance makes that transition structurally unreachable:

```text
-c noinit
-f interface/dummy.cfg
-c "transport select jtag"
-c "set FLASH_SIZE 0x10000"
-f target/stm32f1x.cfg
... inspect Flash registration ...
-c shutdown
```

`noinit` disables automatic initialization, and `shutdown` terminates during
initial configuration processing. The acceptance therefore validates real
OpenOCD configuration and driver registration without requesting adapter
initialization or target examination.

The validator also rejects command lines containing explicit `init`, reset,
halt/resume, Flash erase/write/verify, image load/dump or direct memory
read/write commands.

## Dummy adapter boundary

The runtime file `interface/dummy.cfg` must reduce to exactly:

```text
adapter driver dummy
```

The real binary therefore exercises OpenOCD's own dummy adapter support rather
than a USB/JTAG/SWD device.

The build continues to use the source-pinned OpenOCD runtime declared by
`release/openocd.json`.

## Runtime architectures

The Z2 PS release workflow runs the same acceptance against the packaged
OpenOCD runtime on:

- Linux x86_64;
- Linux ARMv7 Ubuntu 22.04 userspace under the existing QEMU execution layer.

Each architecture retains a JSON evidence artifact including:

- exact ICPN and manufacturer-baseline identity;
- OpenOCD source commit, runtime ID and version banner;
- executable SHA-256;
- dummy-interface and STM32F1 target-script SHA-256;
- observed Flash driver, base, size and target;
- explicit `hardware_runtime_ready=false`;
- explicit `physical_programming_qualified=false`.

ARMv7/QEMU acceptance is PS software evidence only. It is not PYNQ-Z2 or
electrical evidence.

## What a PASS proves

A PASS proves that the actual packaged Plasma OpenOCD executable can, without
hardware initialization:

1. execute the expected OpenOCD version;
2. parse its real dummy interface configuration;
3. select JTAG as a configuration-time transport;
4. parse the real upstream STM32F1 target script;
5. instantiate the compiled `stm32f1x` Flash driver;
6. preserve the exact STM32F103C8T6 64-KiB Main Flash geometry supplied from
   Plasma manufacturer-derived knowledge.

This is stronger than source-text comparison and stronger than the prior fake
OpenOCD subprocess test because the real compiled OpenOCD executable and its
installed Tcl scripts participate.

## What a PASS does not prove

It does not prove:

- adapter initialization;
- SWD or JTAG electrical signaling;
- target detection or DBGMCU identity;
- connect-under-reset behavior;
- target halt/reset behavior;
- Flash erase/program/verify/read;
- OpenOCD RAM loader execution;
- ST-Link, CMSIS-DAP or FPGA adapter behavior;
- PYNQ-Z2 hardware;
- Site target power/reset sequencing;
- Option Bytes or RDP transitions;
- real STM32F103C8T6 programming.

Those remain a later physical HIL gate.

The qualification boundary remains:

```text
hardware_runtime_ready = false
physical_programming_qualified = false
```
