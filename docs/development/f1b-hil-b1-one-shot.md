# F1-B HIL-B1 — true Z2 read-only Identity one-shot (Gate 1 candidate)

**State:** host-only supervisor contract; **live F1-B HIL NOT_RUN / NO_GO**.
This PR does not schedule SWPC, connect to Z2, access MMIO, load a bitstream,
deploy, change driver bindings, or merge. B0 SSH-only basic readiness is already
accepted and is NOT repeated or expanded by this work.

## Exact scope
One PYNQ-Z2 F1-B Image, one 64-KiB PS GP0 window at
`0x40000000..0x4000FFFF`, Site1 only, NO external PL IO.
HIL-B1 is **one supervised load → six allowed Global Identity reads →
original PYNQ base.bin restoration → restoration verified**, never an
external SWD transaction, DUT erase/program or eight-site proof.

The B1 Host contract `pl/hil/fixed_b1_contract.py` provides injected
one-shot state transitions, 64-KiB owner refusal, artifact digest contract
and exact RO Identity checks. No command-line `--execute-live` exists and
no privileged runner/Issue trigger is added by this PR. This prevents
host tests from being mistaken for a device operation.

## Qualified host artifacts
From SWPC Path 2 Run
[39363332124](https://github.com/physicslu/plasma/actions/runs/39363332124),
Artifact [12238640458](https://github.com/physicslu/plasma/actions/runs/39363332124/artifacts/12238640458):
- BIT SHA256: `ad7c525385ae265f8f479acbe4227b2ef97fee51d68ba85b8efeff804bc740f6`
- HWH SHA256: `a367f820e375c7770b7b71c4c7dfee42b64c64eb57fc3d0cdf906a944100ce2e`

Historical known-good `base.bin` SHA256:
`c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`.
Original `base.hwh` SHA256:
`222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a`.

**Blocking gap:** no independent reviewed conversion and SHA256 of an
F1-B FPGA-Manager-compatible `.bin` is in this evidence. Never substitute
SWD-03/04 or PYNQ base BIN for the F1-B candidate. Neither arbitrary
operator-entered digest nor Host BIT digest alone authorizes FPGA loading.

## Host policy tested by CI
1. Preserve exact Host BIT/HWH and known-good recovery hashes; missing candidate
   BIN digest fails closed.
2. Detect bound UIO and platform drivers overlapping **any** of the full
   64-KiB F1-B address window, and any unknown consumer / open PL fd / retained
   mappings. B0 observed `fabric` UIO bound; do NOT unbind automatically.
   The existing SWD-05 four-aperture guard is not sufficient for F1-B.
3. Global Identity RO reads only: +0x000, +0x004, +0x028, +0x030,
   +0x044, +0x048. Require MAGIC=PLSM, ABI=1.0, SWD-only capability,
   Site present bitmap=1, map revision=1, stride=4096.
4. Stage `restore_required` before any candidate-load attempt.
   No blind retry. If a child remains mapped/stalled, **no FPGA reload**,
   persistent `FAIL_OR_UNKNOWN` and independently supervised recovery.
5. Success must include verified original-image restoration and service /
   driver / Boot ID state equivalence; a completed Identity read alone
   is NOT B1 PASS.
6. Tests use injected functions and synthetic dictionaries; no access to
   `/dev/mem`, `/dev/uio*`, sysfs FPGA firmware, SSH, USB or Z2.

## Before real HIL (separate scope and authorization)
- Convert exact approved BIT to Manager BIN using a reviewed Xilinx-compatible
  toolchain, verify converted bytes, create immutable source/bit/hwh/bin
  manifest and an owner-approved candidate BIN SHA.
- Implement and review an actual Z2 privileged one-shot supervisor and
  a non-privileged Owner/Issue #981 dispatch adapter. Reuse proven SWD-05
  recovery policy only after extending the resource guard to 64 KiB.
- Bind an actual ARMv7 native aligned 32-bit Identity reader to the F1-B
  kernel resource; never reuse old SWD-03 register addresses. Isolate
  MMIO in a bounded child, retain a recovery-required marker and
  verify child exit/unmap before original-image restoration.
- Check **only the safety prerequisites tied to the live load operation**:
  current resource exclusivity, usable original-image recovery, relevant
  clock/reset and exact image/board compatibility. These are not new
  HIL-B0 checklist requirements.
- A current bound `fabric` UIO owner or unverified recovery is NO_GO.
  Never unbind drivers, restart services or create fake attestations.
- Use a separately authorized Gate 1 hardware one-shot after any
  necessary code has received independent Gate 2 Merge approval.
  Do not treat this Gate's hosted tests as live Z2 qualification.

**Acceptance boundary:** Host contract PASS != HIL-B1 device PASS. Real
B1 remains NOT_RUN until the missing BIN, owner-safe loader/reader,
supervised recovery and separate hardware dispatch are proven.


## Gate 1 continuation: actual binary derivation and inert live-module integration

An independent local inspection of the exact previously qualified Path 2
Artifact #12238640458 (Run #39363332124) parsed the real Xilinx tagged BIT
envelope for part `7z020clg400`. Payload 4,045,564 bytes; legacy-reviewed
Zynq 32-bit word swapping plus one trailing NOP deterministically derives
a **4,045,568-byte candidate BIN** with SHA256
`c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3`.
This is an **offline-derived candidate, not independently Bootgen-qualified**.
It was not written to any hardware host or FPGA Manager. The tool
`python3 -m pl.hil.fixed_b1_staging --evidence-zip <ZIP> --output-dir <NEW_DIR>`
reads only a pinned BIT/HWH/Host Receipt inside the ZIP, rejects mismatched
source, extracts no archive filenames, and writes an isolated candidate BIN
and diagnostic manifest under the requested new directory.

`pl/hil/fixed_b1_identity_child.py` is a separate native ARMv7 32-bit,
read-only LinuxMMIO child. `pl/hil/fixed_b1_supervisor.py` provides
real Z2 FPGA Manager /proc /sys operations as a **non-CLI target-only library**.
No real hardware route is registered. Its full 64-KiB kernel driver,
UIO, open-device and retained-MMIO scan refuses ambiguous ownership.
An independent root-protected hardware-admission JSON containing
`bootgen_independent_confirmation=PASS`, recovery supervision, and exclusive
ownership is a hard prerequisite. **This admission evidence is NOT created
by the PR or host tests**, so real FPGA loading remains blocked.

The target Supervisor and child are **untested on real Z2**; only their
mocked/hosted tests are in CI. The successful F1-B Host Vivado build and
historical SWD-05 recovery DO NOT authorize F1-B load. Kernel SIGBUS,
uninterruptible AXI stalls and FPGA reload under a mapped consumer remain
significant safety risks. Live operation requires separate review,
privileged Supervisor route and owner authorization after Gate 2.
