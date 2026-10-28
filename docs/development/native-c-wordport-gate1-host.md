# PLASMA Native C WordPort Bridge — Gate 1 / Path 1 / Host-only

**Scope:** source, hosted build, Host-only Protocol A/B tests and Draft PR.
No SWPC/Z2 access, FPGA load, Root installation, OpenOCD/Flash Loader changes,
deployment or real SWD/Flash qualification in this Gate.

## Execution and ownership boundary

The existing `scripts/bluepill-wordport-session.py` remains the only selected
Z2 PS bridge entry point and retains: Root source SHA and trusted-local guard,
ARMv7 barrier SHA preflight, held/tested same-boot Image checkpoint, validated
Manifest and live Root report, global FPGA `port.exclusive()`, `LinuxMMIO`
owner lock, Site 1 `claim_site()`, one owner-private PS-local UNIX socket,
bounded session/idle budget, cleanup and separate guarded Golden recovery.
Under the later owner-approved hardware scope, the total session alarm is
600 seconds and the socket idle timeout is 60 seconds. Both remain bounds on
the guarded owner process.
It now requires an additional **explicit absolute** `--native` ELF path and
`--native-sha256`; missing, replaced, malformed or wrong-architecture native
libraries fail closed. There is no Python fallback to per-bit operations.

Python owns the MMIO mapping and Site lease **for the entire socket session**.
The new `NativeBluepillWordPort` uses a temporary `ctypes.from_buffer` pointer
only within the same process while holding `LinuxMMIO._mutex`, validating
the active Site 1 token and backend state before each bounded C call. The
native library cannot open `/dev/mem`, obtain another lock/lease, configure
the PL, choose an MMIO base, accept socket connections or expose the mapped
pointer to clients. It performs direct fixed-offset 32-bit volatile accesses
on the existing mapping, and reconciles per-operation counts into existing
`LinuxMMIO.stats()` under the owner mutex. No Python per-bit callback occurs.

The C file contains the exact existing OpenOCD Remote Bitbang subset:
`O/o`, `d..g`, `c`, `r`, `B/b`, `Q`; active reset, JTAG, delay and unknown
commands fail closed. It does **not** contain SWD transactions, ACK/parity,
DP/AP access, target erase/program/verify or Flash algorithms. OpenOCD
continues to be the sole source of SWD/Flash control algorithms, locally
on Z2 PS. The PS-local UNIX socket stays owned by Python and is never
forwarded to SWPC.

## Protocol A/B Host-only acceptance

Because the Gate 1 request did not define separate protocol wire formats,
**A and B are test tracks for the same existing Remote Bitbang wire ABI**, not
new device protocols or incompatible OpenOCD modes:

- **Protocol A (direct byte transcript):** admission, `O/o`, `d..g`, sample,
  deassert and quit; negative wrong ABI/unsafe pins, prohibited commands,
  quit tail, poisoned MMIO, released lease and changed native ELF SHA.
- **Protocol B (one local UNIX stream):** fragmented commands and response,
  bounded one-connection ownership/cleanup; negative EOF and command budget.

All synthetic MMIO is backed by a sparse **regular file**, with no hardware
device and no fake DPIDR pass. No functional native C test executes in the
real ARMv7 Linux runtime as part of this Gate.

## Reproduce hosted checks

```sh
PYTHONPATH=software/python python3 -m unittest discover -s software/python/tests \
  -p 'test_native_bluepill_wordport_host.py' -v
PYTHONPATH=software/python python3 -m unittest discover -s scripts/tests \
  -p 'test_bluepill_wordport_session.py' -v
bash scripts/build-native-bluepill-wordport.sh host /tmp/libplasma_wordport_host.so
bash scripts/build-native-bluepill-wordport.sh armv7 /tmp/libplasma_wordport_armv7.so
```

ARMv7 cross-build needs `gcc-arm-linux-gnueabihf`; CI also checks ELF32 ARM
and the actual disassembled `dmb sy` instruction and retains ELF/SHA evidence.
Both shared objects are **build artifacts**, never auto-installed or loaded.
The caller must pin the *exact* ARMv7 artifact SHA before any real session.

## Safety / completion limits

- DMB SY orders CPU memory accesses but does not alone prove PS7 AXI posted
  write completion, mapping memory attributes, physical SWCLK edge rate or
  absence of SIGBUS/AXI stalls. `ctypes` calls can block on an AXI fault.
- A native C library is not an authorization boundary. It must only execute
  inside the guarded Python process; importing it elsewhere grants no Root,
  Site ownership, image integrity or hardware permissions.
- Existing successful Image **Keep Loaded** behavior and separate explicit
  Root `restore` remain intact. A functional failure stops socket activity;
  poisoned/unknown bus or electrical state requires operator-governed
  recovery, not blind MMIO retries or automatic Golden Restore.
- ARMv7 cross-compile and Host-only PASS alone do not qualify real Z2 runtime,
  actual native MMIO access ordering, OpenOCD DPIDR, Flash or readback.
  Hardware execution, deployment and merge were **NOT_RUN** in the original
  Host-only Gate 1.

## Subsequent owner-approved Path 3 hardware scope

At PR HEAD `87ea878fee717b598f0af2e408eb222c9543785b`, an isolated Z2
deployment of the SHA-pinned ARMv7 library read Blue Pill DPIDR `0x1ba01477`
through PS-local OpenOCD, with a simultaneous LA2016 capture. One v0.1
18,768-byte erase/program session then exited 0 with a simultaneous LA capture;
independent readback matched the firmware byte for byte and CDC heartbeat
resumed after one `reset run`. The initial monolithic readback hit the old
60-second Bridge alarm after 12,288 bytes; a separate read-only tail session
completed the comparison. These observations cover the connected prototype,
not general hardware qualification.

The later owner-approved timeout revision sets the total alarm to 600 seconds
and idle timeout to 60 seconds. On the same Z2, one 18,768-byte readback now
completed in a single session with OpenOCD and Bridge exit 0, exact v0.1
SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`,
and safe owner/MMIO release. No additional erase, program, reset, FPGA load or
Golden restore was performed for this timeout revision.
