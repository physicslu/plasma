# PLASMA Z2 Deployment Doctor — safe standalone prototype

This is a **read-only diagnostic and deployment-planning tool**, not a Z2 installer. It is staged in a Draft PR for `physicslu/plasma`, has run read-only over the existing SWPC Path 2 runner (Run #42335593384; Doctor overall WARN), and therefore **does not qualify** any deployment, FPGA Image, Site or target Flash behavior.

## Requirements

* SWPC with Python 3.9+ and Git.
* An existing `physicslu/plasma` worktree; run the script from its root, or specify `--repo`.
* Optional: explicitly identified Z2 LAN IP/DNS name for HTTP checks.
* Optional: pinned SSH known-hosts (`~/.config/plasma/z2-login-known_hosts`) **and key-based SSH** for SSH checks. This prototype deliberately does not load the owner's private password credentials. Password-only setups will be `BLOCKED / NOT_RUN` for the optional SSH segment, not automatically classified as a failed Z2.

## Usage on SWPC

From a clean checked-out PLASMA repository, execute the source-pinned script (or the equivalent owner-authenticated Path 2 Dispatcher operation):

```sh
cd /path/to/plasma
python3 scripts/plasma_z2.py doctor
python3 scripts/plasma_z2.py doctor --host Z2_LAN_IP
python3 scripts/plasma_z2.py doctor --host Z2_LAN_IP --ssh-user xilinx --json > z2-doctor-report.json
python3 scripts/plasma_z2.py plan --route product
python3 scripts/plasma_z2.py plan --route engineering
```

The `z2-doctor-report.json` file in this example is a **local report** created by shell redirection. Do not commit it. Avoid distributing details of your LAN addresses, Git revision, or installed release identifiers.

To use a different **already-pinned** SSH host-key file:

```sh
python3 scripts/plasma_z2.py doctor --host Z2_LAN_IP \
  --ssh-user xilinx --known-hosts /path/to/previously-pinned-known-hosts
```

## Checks and boundaries

| Check | What it proves | What it does not prove |
|---|---|---|
| SWPC source paths / Git HEAD | Local entrypoints/revision and tracked changes | Remote `main` freshness; code qualification |
| SWPC engineering state | Local immutable release IDs are parseable | Same version installed on Z2 |
| TCP :18081 / :18080 | Network listener reachable | Correct application or readiness |
| Bootstrap `/v1/health` | Correct service signature over private commissioning HTTP | Authenticated/publisher-authentic server; production TLS |
| Bootstrap `/v1/status` | Status document returned, B3 capability hint, deployment guard | Physical Bundle activation, engine identity or FPGA load |
| Optional SSH | Pinned-host-key key-based login, ARMv7 architecture, selected unit liveness | Actual board identity, trusted root-owned target profile or programming qualification |
| `deploy` | Always denied | No package, service or device writes |

**Treat `recovery_required` as a hard deployment block.** Missing Bootstrap or Runtime may mean a legitimate unprovisioned factory board; do not auto-install or auto-repair. Never change credentials or bypass host-key pinning to turn a red check green.

Integration baseline: accepted `main` `38b4c0b68fb961b535af9e7a657f242376b9d98d` after PR #1337 (OPF Bundle v3 and Path 2 Install) merged. Worktree synchronization is independent of whether the deployed Z2 has been updated. The source references are `AGENTS.md`, `docs/deployment/ppu-deployment-start-here.md`, `docs/deployment/ppu-bootstrap-factory-and-hil.md`, and `docs/development/ppu-deploy-engineering-modules.md`. The integration-host default `plasmactl deploy` must **not** be mistaken for a Z2 install. The product route uses Bootstrap/Console, and the engineering route uses the separately reviewed `scripts/ppu-deploy` SSH transaction.

## Host-only tests

```sh
python3 -m unittest -q /path/to/test_plasma_z2.py
```

The tests are mocks; they do not access a PYNQ-Z2. Neither this prototype nor these tests constitute a Gate 2 merge or physical HIL approval.

## Joint PR #1337 + #1338 acceptance gate

After collecting an actual SWPC `doctor --json` observation: compare deployed Bootstrap/Runtime evidence against the current accepted `main`, verify target Platform Identity and Engine Selection through existing reviewed mechanisms, reconcile in-flight/coordinator journal and receipt, and only then bind an approved deploy command to one of the **existing** backends. Do not create a parallel SSH writer or new deployment coordinator.
## Path 2 SWPC observation (exact pinned Draft PR)

The existing Issue #981 trusted dispatcher accepts an owner-authored Work Order with
`execution_path=path2-cli`, `capability=operator-cli`,
`scope=guarded-hardware`, `script=scripts/plasma_z2.py`,
`argv=["doctor","--paired-host","--json"]`, and an exact Draft PR HEAD.

`--paired-host` resolves only the hostname from the owner-controlled,
mode-0600 `~/.config/plasma/z2-login-smoke.json` on the actual SWPC worker.
It never outputs passwords or an address. If worker credentials/configuration are
unavailable, the tool fails closed and marks physical Z2 observation NOT_RUN.
No deployment, FPGA load, DUT action, daemon restart or SSH password login.

Real acceptance requires the SWPC `development-execute` runner name, actual
exit status, bounded stdout and job receipt. A hosted test is not Z2 evidence.


## Evidence update — Path 2 live read-only Doctor

- Existing real SWPC Path 2 [Run #42335593384](https://github.com/physicslu/plasma/actions/runs/42335593384) passed the operator CLI exit/receipt. The Doctor overall was **WARN**, not a deployment qualification.
- TCP :18080/:18081, Bootstrap GET health/status, `bootstrap_ready`, `runtime_active`, and a prior `succeeded` deployment were observed. The cited `succeeded` deployment is not independently identified as the OPF Gen7 replacement.
- PR #1337's first deployment dispatch [Run #42338239043](https://github.com/physicslu/plasma/actions/runs/42338239043) failed in `development-authorize` with `WORK_ORDER_MAIN_SHA_NOT_EVENT_PINNED`; SWPC `development-execute` was **skipped** and no Bundle B1/B2/B3 was executed by that request.
- Joint Gate 1 sequence, with independently preserved receipts: (1) source-pinned Doctor precheck; (2) compare Active Asset Set SHA against Gen7/new validated bundle and do not resubmit an already completed transaction; (3) optionally execute authorized Path 2 B1/B2/B3 `mode=activate`, `fpga_load=false` using the existing Bootstrap Coordinator; (4) Doctor postcheck and separate OPF Provider/Active Set validation. Do not turn Doctor's intentionally disabled `deploy` command into an installer.
- No DUT Flash, FPGA reload or OpenOCD Engine switch is in scope. This PR stays Draft pending Gate 2.
