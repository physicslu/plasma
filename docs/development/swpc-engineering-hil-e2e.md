# SWPC Engineering HIL — Manager Batch → Blue Pill CDC

**Gate 1 Draft / Host-only implementation. No hardware test has been performed by this PR.**
Run exclusively on the SWPC engineering host with an owner-authorized, already-qualified
single Site, installed/paired Z2 and an explicitly associated Blue Pill USB CDC port.

This is **not** an alternative programming engine. The SWPC runner calls the
canonical Manager-owned Batch API. OpenOCD remains on Z2 PS. No direct SWD
traffic, FPGA programming, USB hub power, Runtime upgrade, or source deployment
is performed here.

## One entrypoint for Path 2 and Path 3

Both trusted engineering Paths invoke the identical CLI. Current Path 3
already supports owner-approved guarded-hardware Work Orders and native
SSH/USB/TTY tools on the existing `SWPC-plasma-codex` Runner. The earlier
read-only pilot is historical, not a blanket prohibition on Flash. Live
execution must still prove the active worker's effective Linux UID/groups,
USB CDC device ACL, Manager/Console ownership, authorized Z2 transport and
per-Job safety/admission; UID 1000 service ownership must not be inferred
from a different Runner UID or from sandbox configuration. No new Runner
or third approval Gate is required.

```bash
cd "$PLASMA_REPO"  # authorized SWPC engineering checkout
# Preview: validates local firmware bytes and arguments; makes no HTTP request.
./scripts/plasmactl hil programming --profile bluepill-ab \
  --mode smoke --site 2 --ppu-alias z2 \
  --image-v01 /trusted/firmware/v01.bin \
  --image-v02 /trusted/firmware/v02.bin \
  --port /dev/serial/by-id/<verified-bluepill-cdc>
# Real hardware: this flag does not replace the existing Owner authorization.
./scripts/plasmactl hil programming --profile bluepill-ab \
  --mode smoke --site 2 --ppu-alias z2 \
  --image-v01 /trusted/firmware/v01.bin \
  --image-v02 /trusted/firmware/v02.bin \
  --port /dev/serial/by-id/<verified-bluepill-cdc> \
  --execute
```

Substitute real, separately verified local firmware paths; do **not** paste
credentials into CLI args, evidence, PRs or GitHub logs.

## Smoke versus Burn-in

- `--mode smoke`: v0.1 → v0.2 → v0.1; three distinct canonical Batch starts.
- `--mode burn-in --cycles N`: N iterations of v0.1 → v0.2;
  repeat at the **engineering orchestrator** level; product Batch
  `repeat=1` and `retry_limit=0` remain unchanged.
- Each attempt requires one trusted Manager Batch and one Site Job, readback
  SHA256 == input image SHA256, operation-step match, job binding match,
  `safe_off=true`, one submission and an active Resource Set **reused**.
- Then reset/run is inferred from target execution by an exact USB CDC Firmware
  ID + sequential, bounded Heartbeat observation using existing
  `firmware/blue-pill-usb-cdc/host/cdc_probe.py`. v0.1 = 500ms;
  v0.2 = 1000ms. Heartbeat is independent of Flash readback and is not
  external analog SAFE_OFF evidence.

The runner first issues an unconsumed *Manager plan* to check that
`activation_required=false` and `resource.reuse=true`, and explicitly voids
that plan's Start before issuing the canonical Batch Start. It refuses
resource activation. This **is not an atomic resource-activation lock**:
another actor changing the Active Set between preview and Batch admission
could change the Manager's decision. Unattended HIL on a shared PPU requires
an exclusive owner/maintenance admission guarantee; do not represent this
two-step check as race-free. The PPU's existing Root/Site gates remain active.

## Results / operating boundary

Evidence lives in a private per-run folder (default
`~/plasma-engineering-hil`), holding sanitized Batch/Run receipts,
per-attempt CDC logs and one summary. Input firmware bytes and credentials
are not written to the evidence folder. On timeout/lost POST response or
unexpected Manager identity, **do not POST again**: preserve the Start ID
and use read-only `GET /api/programming/starts/{start_id}` to reconcile.

The CLI tests the **Manager → Gateway → Z2 PS/PL → DUT → USB CDC** path.
It does not itself click the Browser UI; Browser P/E Mode E2E requires a
separate UI automation check before calling the entire Control Station
product E2E PASS. A CDC port chosen by the operator is not cryptographic
proof of Site-to-cable wiring: verify that fixture association before live
test. Multi-Site concurrency and factory acceptance are not covered.

This tool must not be invoked automatically from arbitrary public-repository
PR events, and it never performs a Control Station deployment. A future
`plasmactl acceptance full` composition can sequence reviewed deployment,
readiness and authorized HIL without changing either independent entrypoint.
