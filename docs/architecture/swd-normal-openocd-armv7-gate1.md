# SWD NORMAL / PS ARMv7 MMIO Gate 1 Host-only boundary

**PR #1189 Draft.** This is a source-only integration contract, **not** an
actual OpenOCD C adapter, Linux driver, deployed Image or DUT qualification.

## NORMAL transaction compatibility contract

`software/python/plasma_interfaces/swd_native_normal_contract.py` models
the proposed OpenOCD SWD adapter callbacks `read_reg`, `write_reg`,
`switch_seq` and `run`, using the existing `SwdSiteController` as
the **single source of register sequencing and command encoding**.

- Caller must already own and verify exact Image/Manifest, exclusive Site
  lease, ABI v5 identity, qualified voltage and NORMAL mode. The module
  neither grants privileges nor opens any device.
- 16 entries is the bounded host queue, separate from the FPGA's 16-entry
  per-Site command/response FIFO. This prototype executes the queued
  operations **one at a time**; higher-throughput native pipelining is pending.
- Results preserve exact tag order, raw ACK and read data-valid. WAIT, FAULT,
  invalid ACK, timeout or uncertain MMIO **block** the adapter instance.
  No silent retries or write replays; no fabricated AP posted-read/RDBUFF.
- SWJ is one 1..256-bit LSB-first command (or 64-clock line reset). All
  physical SWCLK generation remains inside the independent PL FSM, not Linux.
- Site 1 and Site 2 are independent AXI windows. No MPE manager, no global
  SWD scheduler and no fallback to GPIO/WordPort or old remote_bitbang route.
- **Native C OpenOCD adapter = NOT_IMPLEMENTED.** Exact-version OpenOCD API,
  build, binary and target tests = NOT_RUN. Existing production OpenOCD
  0.12.0 remains untouched.

## ABI v5 native LinuxMMIO / Site Lease integration (Host-only)

The project now supplies `swd_native_linux_mmio.py` with
`swd_site_aperture(site_id)` and `SwdNativeLinuxMMIOPort`. These reuse
the existing `LinuxMMIO` and `SiteMMIO` ownership/mapping APIs, plus
the existing SHA-pinned `ARMv7DMBBarrier`, rather than opening an alternate
driver/backend or resurrecting the old bitbang WordPort.

- The independently leased Site 1/2 bases are **candidates**
  `0x43C01000` and `0x43C02000`; they still require exact-HWH verification.
- Readable registers: `00 04 08 0C 18 1C 24 28 2C 30 34 38`.
  Writable registers: `08 0C 10 14 20 28 2C 30 34 38 44 48 4C
  50 54 58 5C 60 64` (hexadecimal byte offsets). Any other offset,
  including retired SWD Debug offsets `0x3C/0x40`, is denied locally
  without MMIO. The hardware additionally returns SLVERR for them.
- The adapter requires an **already-open** `LinuxMMIO`, an exclusive
  correctly numbered `SiteMMIO` lease and its exact per-Site access policy.
  No FPGA download, Root authorization, voltage authorization or OS
  privilege is acquired by construction.
- ARMv7 hardware access requires `ARMv7DMBBarrier`; an injected fake
  barrier is allowed ONLY on a non-symlink REGULAR FILE under Host-only CI.
  Barrier uncertainty poisons the **entire shared LinuxMMIO mapping**, not
  merely one Site. The associated Source/Test cases cover 2-Site ownership,
  v5 identities, wrong Site/ABI, retired offsets, invalid width, symlink,
  stale lease and cross-Site fail closed.
- `LinuxMMIO` currently implements native CPython
  `memoryview(...).cast("I")` word reads/writes. These tests **do not
  prove ARMv7 LDR/STR instructions, Device memory page attributes,
  posted AXI completion or physical bus abort recovery**. ARMv7 ELF/
  disassembly and real PS7/PL/MMIO qualification remain NOT_RUN.

## Exact OpenOCD 5088db4c source API mismatch (C Adapter still pending)

PR #1196 used OpenOCD `0.12.0+dev` source
`5088db4c9154ca833c6d558381074b33672e127a`, **not** the
`v0.12.0` release. Its
`src/jtag/swd.h` `struct swd_driver` has
`init(void)`, `switch_seq(enum swd_special_seq)`,
`read_reg(uint8_t cmd, uint32_t *value, uint32_t ap_delay_hint)`,
`write_reg(uint8_t cmd, uint32_t value, uint32_t ap_delay_hint)` and
`run(void)`. OpenOCD's command-byte bit layout is **not** the private
9-bit FPGA `encode_transfer` layout. A real C adapter must decode
SWD APnDP, RnW, address and parity, preserve queued result-pointer lifetime,
correctly handle AP delay hints, DPv2 TARGETSEL/no-ACK special behavior,
WAIT/FAULT/uncertain write semantics, and real SWJ sequence enumeration.
A Python method name match is **not** source-level API compatibility.

A pinned source-level Host-only bridge now exists as
`swd_opencd_5088_command_contract.py`. It validates OpenOCD `swd_cmd()`
parity, APnDP, RnW and DP/AP register offsets, translates command bytes into
the **different** PLASMA private 9-bit command through the shared
`SwdNativeNormalContract`, and supports explicit 1..256-bit LSB-first SWJ
payloads. Cross-layer tests assert that OpenOCD DP IDCODE read `0x24`
becomes FPGA private `0x02`, while OpenOCD AP write `0x3A` becomes
private `0x0D`. They also test 64/136/224-bit atomic sequences and negative
callback direction/parity/length cases.

**Important fail-closed scope gaps:** OpenOCD's `ap_delay_hint > 0` is
rejected rather than guessed as the FPGA's hardcoded 8 idle cycles; DPv2
no-ACK TARGETSEL is rejected rather than falsely claiming an ACK. The real
`enum swd_special_seq` mapping, OpenOCD queue result-pointer lifetime,
AP posted-read ordering/RDBUFF, error-code conversion, C driver integration
and native cross-compilation are still **NOT_IMPLEMENTED**.

The Python contracts remain Host-only; the standalone C core and callback
slice below are now implemented, but **OpenOCD adapter registration and real
OpenOCD binary integration are not**.

## Native C SWD FIFO core and OpenOCD 5088 callback slice (Host-only)

The new `software/native/swd/plasma_swd_fifo_core.[ch]` is an actual
C implementation of the private **ABI v5 register-level transaction queue**,
not merely the earlier Python contract. An external pre-authorized and
already-leased C word-access backend injects read32, write32 and a write
barrier; construction never opens `/dev/mem`, claims a Site, loads an
FPGA Image or creates a Socket. No device-backed C backend is implemented
or admitted in this Gate 1 increment.

- It checks Site1/2 identity `0x00050001/2` and admits only OFF→NORMAL;
  bounded queue depth 16; translates OpenOCD SWD cmd byte parity/direction
  into the private SWD FIFO command; supports exact-byte 1..256-bit LSB-first
  SWJ staging; sequential 16-bit tagged FIFO completion, explicit barrier,
  raw ACK and data-valid validation. Read result pointers are committed
  only after the **whole queued batch** succeeds.
- WAIT/FAULT/invalid ACK, MMIO/barrier uncertainty, timeout or mismatched
  tag poison the adapter and forbid implicit replay of a possible DUT write.
  AP delay hints and DPv2 no-ACK TARGETSEL are **explicitly unsupported**
  rather than silently represented as a normal SWD transfer.
- `plasma_swd_openocd5088_callbacks.c` binds the C core to the
  `struct swd_driver` callback signatures from the pinned OpenOCD
  `5088db4c9154ca833c6d558381074b33672e127a` source. It references
  the canonical `swd_seq_*` arrays from OpenOCD's header rather than
  synthesizing an alternate SWJ bitstream. A Host-only C compilation test
  uses an **explicit test declaration shim**, not real OpenOCD object files.
- **Not delivered:** OpenOCD `struct adapter_driver` CLI/transport
  registration, a trusted C-owner/lease-MMIO binding, full OpenOCD executable
  compilation against the exact original headers and API, ARMv7 ELF/HIL,
  AP posted-read compatibility through the complete ADIv5 stack, GIC,
  external SWD timing and any DUT programming. The C callback slice is
  **not** a selectable or deployable OpenOCD adapter yet.
- GitHub-hosted `test_swd_native_c_compilation.py` compiles/runs C
  with `cc -std=c11 -Wall -Wextra -Werror` and fake MMIO. This validates
  real C execution and error handling without asserting physical acceptance.

## Source-locked upstream OpenOCD adapter registration (Host-only CI)

OpenOCD `src/target/adi_v5_swd.c:swd_select()` invokes
`swd_driver.init()` during *transport selection*, BEFORE
`adapter_driver.init()`. This makes the two init callbacks fundamentally
different: SWD transport-selection init must be inert; the actual
`adapter_driver.init()` and each I/O callback enforce externally verified
per-Site ownership/lease admission. Host-only tests now assert that SWD
transport selection succeeds while device initialization without an
explicit admitted Site **fails closed**, including after a terminal error.

The dedicated `plasma_swd_openocd5088_driver.c` now provides
`struct adapter_driver plasma_swd_adapter_driver` for the pinned
OpenOCD `5088db4c9154ca833c6d558381074b33672e127a` tree. It is
an SWD-only adapter with the existing `struct swd_driver` callbacks,
no JTAG interface, no Debug Bitbang and no GPIO fallback.

The source-lock injector `scripts/ci/inject-plasma-openocd5088-native.py`
requires the exact pristine OpenOCD commit and then applies only four
PLASMA C/header files and narrow upstream registration/Makefile changes
to an **ephemeral GitHub-hosted checkout**, never to Production OpenOCD.
The existing `Python and PL source tests` Workflow contains a
separately routed, GitHub-hosted native-build job which compiles the
real source and checks both selectable-adapter registration and
**fail-closed initialization before any owner/lease binding**. The
earlier test declaration shim cannot establish upstream source compatibility.

**Deliberate access boundary:** the standalone adapter has no
PS device-backed C word I/O, Image/Manifest/Root admission or
Site lease binding. Even if a source-locked OpenOCD binary compiles and
the `plasma_swd` name is selectable, `init` must fail without an
authorized admitted Site. Do not interpret a successful build or
negative admission test as target SWD, AP posted-read, Flash or HIL PASS.
Production packaging and live execution remain excluded from this PR.

## Native C Site Lease word-access seam (Host-only; PS owner still pending)

`software/native/swd/plasma_swd_lease_word_port.[ch]` now exposes a
C-only, **inert** lease-qualified `struct plasma_swd_word_io` adapter.
It is a thin ownership/ABI guard around a provider that the future
PS-local runtime must supply. It does **not** open `/dev/mem`, mmap a
physical window, duplicate the LinuxMMIO device mapper, obtain a new
Site lease, embed Python in OpenOCD or introduce a socket/middleware.

- Explicit `site_id` (1/2), candidate AXI base and nonzero
  `lease_generation` identify each independent Site. Constructing it
  touches no device; the explicit `admit` calls the owner's trusted
  qualification hook. Revoked, stale or fork-inherited leases reject.
- Each `read_owned/write_owned/barrier_owned` provider callback
  **must atomically revalidate** Image/Manifest, Boot/Root and electrical
  qualification plus current Site ownership under the existing shared
  device/owner lock **together with** the 32-bit MMIO operation.
  A one-time `qualify` flag is never sufficient for hardware safety.
  If the privileged provider cannot guarantee this, it must fail closed.
- Exact ABI-v5 32-bit offset allowlists are duplicated *only as contract
  constants* at the Python/C seam and covered by Host-only tests.
  Cross-Site, unaligned, write-only/read-only confusion and the retired
  `0x3C/0x40` SWD Debug offsets are rejected **before** calling provider I/O.
- A failed owned I/O or Barrier marks the port unusable and invokes
  `invalidate_all` on its central owner domain so peer Site accesses are
  rejected until explicit safe requalification. The C wrapper cannot
  recover kernel SIGBUS, AXI hangs or unknown write completion.
- The GitHub-hosted C tests use a deterministic **synthetic owner** with
  two Site generations, authorization flags and register responses; they
  demonstrate the C FIFO working through the new guard as well as fail-
  closed stale lease, missing voltage, retired offsets and uncertainty.

**Remaining blocker:** this repo has **not** yet supplied a trusted
PS-local, device-backed provider, ARMv7 MMIO load/store/Barrier HIL,
LinuxMMIO cross-process owner-lock enforcement evidence or a real
OpenOCD `plasma_swd_openocd5088_bind` call wired through this guarded
port. A mock success is not Image/Manifest authenticity, electrical
qualification or permission to access hardware. C/Python both describing
the Site contract is not the same as sharing one live object or lock.

## PS-local shared advisory MMIO owner lock (C ↔ Python, Host-only)

The standalone C lock primitives in `plasma_swd_owner_lock.[ch]`
use the **same** `/run/lock/plasma-mmio.lock`, `O_CREAT|O_RDWR|
O_CLOEXEC|O_NOFOLLOW` and nonblocking exclusive `flock()`
semantics as existing Python `LinuxMMIO.open()`. A non-hardware test
compiles a C subprocess and checks **both directions**: while Python
holds the test lock C cannot acquire it, and while C holds the lock
Python LinuxMMIO cannot open its synthetic regular-file backend.
Symlink lock paths are rejected. No live Z2 lock/device was touched.
The default OpenOCD C build **hard-rejects alternate lock paths**, even
when absolute; only `-DPLASMA_SWD_HOST_TEST=1` in the separate hosted
regular-file C test binaries permits temporary lock paths. Source-locked
OpenOCD is built without this flag. The negative test compiles both
variants and checks that the production variant rejects an arbitrary
pathname *without creating a file*.

`plasma_swd_lease_word_port_init()` now **requires an already-held
process-owner lock** (not merely a provider callback); all later Site
admission, reads, writes and barriers check creator PID, live lock,
and its acquisition epoch. Release/reacquire cannot revive a stale
Site token. Both Sites within one PS-local process may use one common
process lock, plus independent per-Site lease generation/authorization
inside the trusted provider.

**Limits:** `flock()` is an advisory cooperative process exclusion,
not cryptographic trust, not proof of loaded Image/Manifest, not
protection from kernel drivers or another privileged process that
ignores the lock. `valid()` verifies process/descriptor bookkeeping
only, not kernel owner provenance. A production C provider must
still authenticate applicable Root/boot/board/electrical state and
perform each native 32-bit MMIO operation under the same authoritative
hardware-owner mutex and Site lease. This PR does not implement any
real device-mapped provider, a C-to-Python memory sharing ABI, or a
deployed OpenOCD startup admission mechanism. Never use Host-only
regular-file evidence as HIL acceptance.

## Two-level Site ownership — ADR-0007 (Host-only implementation)

The revised owner-approved Gate 1 implements the Host-only lock protocol
documented in [ADR-0007](../adr/0007-ppu-reload-fence-per-site-locking.md).
The existing global PPU file `/run/lock/plasma-mmio.lock` is now used
as a **shared** programming fence when explicitly selecting one exact
SWD Site. A separate `.site-1` or `.site-2` file is taken EX.
The default, historic `LinuxMMIO` remains global EX and is unchanged
for existing callers. C `plasma_swd_owner_lock_acquire_site()`
follows exactly the same ordering; no alternate pathname may be used
in the real build.

Protected `RootZ2TargetPort.exclusive()` keeps its original
`supervisor.lock` EX and adds the **same PPU MMIO fence EX** before
loading/changing/restoring any FPGA Image. The Root Source Pin,
Image/Manifest hashes, existing protected owner checks and Golden
recovery decisions are still independent mandatory conditions.
No Site can enter while Root holds PPU EX; Root cannot take PPU EX
while either Site holds SH. Different Sites can hold SH concurrently,
but only one process can take each Site EX. Host-only tests exercise
these conditions with actual separate local C/Python processes and
file-backed MMIO; they are NOT a DUT, a physical FPGA Reload or HIL.

**Remaining qualification blockers:** root-owned/service group file
permissions on real Z2, exact-SHA protected Root source pin rollout,
live FPGA Image/Boot/voltage attestation per Site, active OpenOCD C
Owner binding, native ARMv7 width/Barrier, actual two OpenOCD
processes executing FPGA SWD concurrently and the eight-Site physical
product. One `active_site` per OpenOCD process is acceptable only
if each process owns a distinct Site lock; it is not evidence of
full multi-DUT throughput. Do not deploy solely on mock CI.


## PR #1199 Native C evidence reused — ABI v5 word accessor (Host-only)

Merged [PR #1199](https://github.com/physicslu/plasma/pull/1199),
head `e6dfb727cc687353fde3649e5e7775e3ffa37a46`, is a
**physical Z2 prototype proof for the OLD single-Site Remote Bitbang
Image**, not an ABI-v5 SWD FIFO qualification. The merged Native C
bridge performed ARMv7 volatile `uint32_t` MMIO accesses and
`DMB SY` under the **already authorized** Python process mapping,
with the actual DPIDR `0x1ba01477`, 18,768-byte Flash readback
SHA256 `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`
and a successful 600-second bounded session / 60-second socket idle
revision. None of those physical receipts apply to the v5 Image, the
v5 FPGA FIFO or two concurrent DUTs; the old Remote Bitbang protocol,
clock toggling and Python per-bit route must NOT be reintroduced.

For v5, new `software/native/swd/plasma_swd_native_words.[ch]`
uses only the **reusable native access technique**: externally
provided aligned, exactly 4096-byte existing mapped
`volatile uint32_t *`, ARMv7-A `DMB SY` on real ARMv7 and a
compiler fence for non-ARM Host-only tests. It is a C
`plasma_swd_lease_provider` for the existing C Lease Word Port,
not a separately privileged device opener, Python per-bit callback
or Bitbang SWD engine. Every access independently checks
current process/lock epoch, exact Site ID/base/generation and
a required trusted, same-process **native C authorization callback**
for Root source/Boot/Image+Manifest/Site lease/voltage. Wrong ABI,
forbidden register offset (including retired 0x3C/0x40), missing
authority and revoked/uncertain ownership deny. Failures poison the
shared owner domain via `revoke_all`.

Host-only C tests use two synthetic 4-KiB pages and an injected
attestation function to exercise the real native read/write interface,
per-Site isolation and fail-closed behavior. GitHub-hosted ARMv7
cross-build inspects **ELF32 ARM, word LDR/STR and DMB SY**, following
the proven #1199 source/build evidence pattern. These proofs mean
**C code was compiled with target instructions**; they do **not**
establish Device memory attributes, AXI write completion, physical
atomicity, SIGBUS containment, mapping provenance or Image approval.

The crucial still-missing connection is a **trusted Z2 PS-local
process** that obtains the guarded device mapping and supplies the
real native C authorization callback/Root+Manifest state to this
provider and binds an admitted FIFO to the OpenOCD
`plasma_swd_openocd5088_bind()` entry point. The new driver is
not auto-bound and OpenOCD must continue to reject unowned `init`.
The 600/60 timeout revision in #1199 was specific to its old
PS-local Socket bridge, **not** a v5 FIFO/OpenOCD timeout selection.

## OpenOCD C Adapter owner-bound FIFO admission (Host-only)

The former `plasma_swd_openocd5088_bind(fifo)` accepted only an
`admitted` boolean and could not prove that the FIFO used the qualified
C ABI-v5 word accessor. It is **removed**. The only C binding entry
is `plasma_swd_openocd5088_bind_guarded(fifo, lease, native)`,
declared by `plasma_swd_openocd5088_binding.h`. It rejects an arbitrary
pre-admitted FIFO and enforces identical Site ID / base, lease
generation, **exact separately locked Site ownership**,
`plasma_swd_lease_word_port` I/O function pointers and the trusted
Native Word provider context. A legacy global-exclusive lock is not
accepted as evidence of an independent Site session.

`plasma_swd_openocd5088_owner_ready()` reevaluates the same bound
lease and the **trusted native C authority callback** before
OpenOCD Adapter init, read, write, SWJ or run; failures block/clear
the FIFO to prevent queued writes from being replayed after an
Image/voltage/lease change. `adapter_driver.quit()` clears and
invalidates the session without attempting uncertain MMIO cleanup.
The underlying Native Word provider continues to check the authority
at every volatile 32-bit transaction.

**Security limit:** the authorization callback is an external
trusted-PS integration requirement, *not an attestation mechanism
implemented by this PR*. The Host-only mock callback can simulate
Root/Image/Boot/Manifest/voltage revocation, but cannot establish
real Z2 source pin authenticity or a safe FPGA Image. There is
still no privileged real PS device mapping owner, no startup command
to bind an admitted v5 Site in production, and no Z2 HIL.
A selectable OpenOCD Adapter must continue failing init when unbound.

## PS-local preopened-FD mmap lifecycle (Host-only, no Root approval)

`software/native/swd/plasma_swd_ps_mapping.[ch]` now adds an
**explicit Native C Linux mmap/munmap lifecycle** for one ABI-v5 Site.
The mapping function accepts a **borrowed already-opened FD** from a
future trusted PS-local owner; it does not open `/dev/mem`, invoke
Python per-bit callbacks, load an FPGA Image, or acquire Root privilege.

Before mapping, it requires the ADR-0007 per-Site exclusive lock,
canonical physical aperture, nonzero Site lease generation,
`FD_CLOEXEC`, read/write access and a successful independent C
authorization callback. Production accepts only the `/dev/mem`
character device type (Linux major=1, minor=1) with `O_SYNC`;
the separate `PLASMA_SWD_HOST_TEST` build instead **rejects device
nodes** and maps only a large sparse regular file. `mmap(MAP_SHARED)`
maps one precisely 4KiB aligned Site page and initializes the Native
C 32-bit Word Port. A second authorization recheck follows the map
before the page pointer is exposed. No read/write SWD transaction
occurs merely by attaching a map.

Host-only tests check both Site 1 and Site 2 map from a synthetic
file, correct Site isolation, v5 identity, native FIFO admission,
non-root fake authorization revocation, read-only FD refusal,
wrong Site/lease refusal, double-attach refusal and borrowed FD
ownership on detach. The `swd-openocd-native` GitHub-hosted job
includes the C object in the exact-source OpenOCD link and
cross-compiles the mapper for ELF32 ARM. The proven ARMv7 native
word `LDR/STR/DMB SY` disassembly checks remain independent.

**Trust boundary remains BLOCKED:** this is a device-backed *mapping
mechanism*, not a trusted Root admission provider. The protected
Root source currently handles Image download/test/restore but exposes
no approved ongoing v5 Site/Manifest/voltage authorization API.
A caller could supply an untrustworthy callback; **such a callback
does not make hardware operation safe**. The actual Z2 OS permissions,
Root Source Pin, current Boot ID, loaded Image/Manifest, board voltage,
AXI Dev-memory attributes and error/UNKNOWN recovery cannot be
asserted by this Host-only test. No deployed OpenOCD launcher calls
`plasma_swd_ps_mapping_attach` and no hardware is operated.
The correct sequence for a future trusted owner is: protected
Root evidence and Site admission → acquire PPU SH + Site EX →
obtain and hold valid MMIO FD → Native C map → Lease Port/FIFO
admission → guarded OpenOCD bind → bounded operations → unbind →
retire/unmap → close borrowed FD with owner → release Site then PPU.
Any uncertain operation must remain blocked, never replayed.

## Live Root/Image evidence boundary — fail-closed C contract (Host-only)

Inspection of the current protected code exposes a decisive limitation:
`pl/hil/fpga_image_guard.py:read_live_z2_facts()` explicitly returns
`active_image_attestation="UNPROVEN"` and
`axi_isolation_evidence="UNPROVEN"`. Its persistent journal
(`pl/hil/fpga_image_root.py:read_state()`) records a `session_id`,
`boot_id`, Manifest and firmware hashes and an Image state, **but is
not proof of loaded FPGA configuration bits**. The existing protected
Root `download/test/restore` operations do not provide an ongoing
native-OpenOCD Site admission API. These are **Gate 1 blockers**, not
features that a Mock or saved JSON file can mark PASS.

`software/native/swd/plasma_swd_owner_evidence.[ch]` adds a small
**typed native C evidence comparison contract**, intentionally not
a new attestation issuer, per-Image token, registration record or
additional approval Gate. Its expected reference includes the
existing Root journal `fpga-<32 hex>` session ID, Boot UUID,
source-pinned Root executable SHA256, paired Manifest SHA256,
actually *loaded* Image SHA256, Image ID, ABI version 5 and Site mask.
An independent trusted same-process observer must remeasure those
values **during each Native C MMIO operation**, including current
Manager state, actual loaded-Image attestation, AXI isolation,
complete other-owner scan, qualified voltage and available recovery.
All claims must be complete, valid and identical to the frozen Root
reference. Every missing, changed, unknown, revoked or failed read
terminally blocks that C owner session and cannot automatically revive.
The existing ABI-v5 `plasma_swd_native_words` callback accepts
`plasma_swd_owner_evidence_authorize()` and
`plasma_swd_owner_evidence_revoke_all()`.

Positive tests deliberately use *synthetic* expected/live observations.
Negative tests cover current Root's **UNPROVEN** Image and isolation
claims, Boot/Root/Manifest/Image drift, Image session drift, manager
state, Site mask, lease generation, missing voltage/recovery, failed
observer and no replay after revocation. This establishes only C
contract behavior, not any Root authentication or physical Image
proof. The expected snapshot and observer are **not trust anchors** if
supplied by the same unprivileged process; never deploy them that way.

Before physical use a protected PS-local integration must **prove**
the actual current-boot Image/Manifest/Root identity, AXI isolation,
owner/lock/DAC and electrical preconditions, and must install a
source-reviewed live measurement provider. Importantly, current Root
source still says `UNPROVEN`, so this contract **cannot authorize
the existing Z2 state**. Opening the Site MMIO FD, attaching C
mapping or binding OpenOCD does not remedy that absence. No Z2,
SWPC or DUT operation is performed by this change.

## ARMv7 MMIO word width contract

`software/python/plasma_interfaces/swd_mmio32_contract.py` checks
aligned, unsigned 32-bit accesses within one 4-KiB Site window, and
requires explicitly injected `read_word`, `write_word`, read-barrier and
write-barrier implementations. It deliberately does **not** open
`/dev/mem`, `/dev/uio`, mmap, Socket or an OS privilege boundary.

Mock tests demonstrate 32-bit **function calls and ordering only**. They
do not prove that CPython emits ARMv7 LDR/STR instead of byte stores.
`struct.pack_into("<I", ...)` cannot be substituted for architectural
MMIO width and ordering evidence.

Still blocking: target-specific native 32-bit access width qualification,
ARMv7 disassembly (LDR/STR, DMB) and Device mapping attributes; PS7 AXI
error/interrupt admission; fresh exact-HEAD Vivado Timing/DRC/BIT/HWH;
actual Z2 HIL; version-qualified OpenOCD Native C adapter.

**Status:** HOST_ONLY_CONTRACT_CANDIDATE, ARMV7_NATIVE_WIDTH_NOT_RUN,
OPENOCD_NATIVE_C_ADAPTER_NOT_RUN, EXTERNAL_IO_TIMING_BLOCKED,
DRAFT_NO_MERGE_NO_DEPLOY.
