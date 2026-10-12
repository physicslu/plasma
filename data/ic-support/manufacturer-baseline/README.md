# Manufacturer-only Programming Baseline

This directory is the isolation boundary for manufacturer-derived programming knowledge.

The first target is `STM32F103C8T6`, chosen because it is the nominal MCU used by the
user's Blue Pill board and because the repository already contains an admitted exact ICPN
for that device. A Blue Pill board name is not accepted as silicon identity; physical
qualification must still read and verify the actual fitted device.

## Scientific control

Phase A is deliberately independent from programmer implementations:

```text
ST manufacturer documents
        |
        v
Device + Programming knowledge
        |
        v
machine-readable program model
        |
        v
frozen SHA-256 baseline
```

Before the baseline lock exists, the derivation must not read or use backend source code,
backend target configuration, backend flash-driver behavior, adapter-speed defaults, or
third-party programmer implementation details.

The lock freezes the exact JSON bytes. Only after that freeze may Phase B independently
inspect a backend implementation and compare semantics. Phase B must never silently
rewrite the manufacturer baseline.

## v1 scope

The v1 baseline captures:

- exact STM32F103C8T6 identity context;
- operating VDD/I/O/VDDA characteristics;
- Flash/SRAM/system-memory/option-byte map;
- SWD and JTAG programming/debug signal requirements;
- explicit `unknown` manufacturer SWD/JTAG clock limits where the locked documents do
  not publish numeric min/max/recommended values;
- Flash programming electrical range;
- 1 KiB page erase geometry and 16-bit programming granularity;
- FPEC register addresses, unlock keys, status/control bits;
- machine-readable unlock, half-word program, page erase and mass erase sequences;
- read/write protection and destructive recovery boundaries.

The model is research data and code. It does not perform hardware I/O and keeps
`hardware_runtime_ready=false`.

## Validation

```bash
python data/ic-support/manufacturer_program_model.py
python data/ic-support/manufacturer_program_model.py --signature
python data/ic-support/test_manufacturer_program_model.py
```

The validator fails closed on baseline digest drift, geometry drift, backend-derived keys,
invented SWD/JTAG speed values, sequence drift, or any attempt to promote the baseline to
hardware-ready state.

## Phase B — post-freeze OpenOCD comparison

Only after freeze commit `2296863cd7c68d76c5e18a6db08fe6e319ebf4cd` was created did the pilot inspect the Plasma-pinned OpenOCD `v0.12.0` source at commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.

The comparison is intentionally one-way:

```text
frozen manufacturer baseline
          |
          +---- compare ----> OpenOCD implementation
          |
          `---- remains immutable
```

The comparison records exact semantic matches separately from backend optimization,
backend defaults, manufacturer-unknown values and specification conflicts.

Key result:

- core FPEC register/key/status/page/half-word/erase/program semantics match;
- OpenOCD adds target-halt policy, software timeouts and a RAM-resident async Flash loader;
- OpenOCD's target configuration chooses a 1 MHz adapter default from its reset-clock
  assumption; that value is **not** promoted to a manufacturer SWD/JTAG speed limit;
- the OpenOCD Blue Pill board file overrides Flash size to 128 KiB while warning that a
  nominal C8 may then be used outside specification. The exact STM32F103C8T6 Device
  Profile remains 64 KiB;
- OpenOCD's GD32 compatibility handling is useful implementation evidence but must not
  redefine ST exact-ICPN identity.

Run:

```bash
python data/ic-support/compare_manufacturer_openocd.py
python data/ic-support/test_manufacturer_openocd_comparison.py
```
