# Path 2 — project-agnostic FPGA image loader core (Gate 1)

**Status: source-only core; trusted-root backend and live Path 2 routing
NOT REGISTERED.** This draft corrects the mistaken idea that Path 2 itself
is entirely F1-B-specific: the Dispatcher/Work Order and host Build Engine
are shared, but existing selected host build and privileged target root
entry remain F1-B/fixed-project-bound.

## Scope and minimal reuse

`pl/hil/path2_generic_image_loader.py` provides a typed, exact immutable
project/image/recovery manifest; exact SHA-256 verification of candidate
BIT/HWH/BIN and original recovery BIN/HWH; rejects arbitrary file paths,
symlinks, digest mismatch, manifest extras or reused candidate/recovery image.
It reuses **existing** `one_shot.run_sequence` for ordered
preflight → durable recovery intent → candidate load → test →
restore original → verify restoration; an uncertain restore is elevated to
`UNKNOWN_MANUAL_RECOVERY_REQUIRED`, with a protected RootBackend
supplied only by trusted installed code.

It does **not** register a new CLI, Runner, Workflow, Dispatcher Task,
SSH/sudo route, project selector in `main`, or arbitrary privileged
`fpga_manager` write. No branch-supplied manifest grants admission.
Hosted fake backend PASS tests prove ordering/negative contracts only.
They do not prove physical reconfiguration, bus quiescence or recovery.

## Already-implemented generic one-shot API (not a Path 2 stage route)

`pl/hil/swd04/one_shot.py::run_live(inputs, profile=...,
test_callback=..., admission_check=...)` **already allows an injected
hardware profile, test callback, and independent admission callback**.
It has existing FPGA Manager write/rollback and owner-lock primitives, so
this Draft must not be described as inventing a new physical loader.
However, that call runs a **one-shot load/test/restore**, not the held
three independent Path 2 stage transactions. Its legacy result schema
also explicitly assumes external DUT/SWD **NOT_RUN**, and its loaded
receipt/ownership checks require profile-specific hardware qualification.
A PYNQ-Z2 image driving external SWD must not reuse the internal-only
proof as authorization to connect or program Blue Pill.

The new `ImageProfile` and byte-level contract are an **offline immutable
manifest/admission layer**. `supervised_one_shot` delegates the stage order
to the existing `one_shot.run_sequence` and requires an externally
injected, protected backend; it does not clone FPGA Manager writes.

## Why this is not yet an operational generic Path 2 loader

The present trusted `scripts/plasma_development_stage_transport.py`
still targets `/usr/local/libexec/plasma/z2-path2-f1b-root-entry`, and
`pl/hil/path2_f1b_minimal_stage.py` implements held Download/Test/Restore
for exactly F1-B. `scripts/plasma_path2_runtime_integration.py` also
guards its Build and Stage project as `z2-fixed-unified-site1`.
Replacing a filename to bypass those checks is prohibited.

The second step must be a separately code-reviewed **protected-root
profile backend** and exact reviewed Work Order binding, reusing the
current shared Runner/Stage Transport rather than adding an alternate
privileged path. It must enforce root-owned source+firmware manifest,
immutable source SHA, original-image hash, device/clock/driver/proc
ownership and AXI safety, current boot and FPGA Manager state, durable
intent before any write, bounded child/lock, and independently verified
restoration. Development acceptance must include real SWPC/Z2 receipts
before Gate 2 readiness; do not treat these mocked callbacks as that proof.

### Direct Blue Pill application

The requested project is
`pl/projects/z2-bluepill-rbb` (Draft PR #1142) with a candidate 4-KiB
GP0 aperture at `0x40008000`. Candidate BIT/HWH/BIN SHA256, original
image current-boot availability, SWD wiring/VTref/GND, real DPIDR and
program/readback remain **NOT_RUN / UNKNOWN**. The archived F1-B
`base.bin` hash is not a live admission.

No WEB testing, merge, deployment, SWPC/Z2/DUT operation or Flash writing
is performed by this PR.
