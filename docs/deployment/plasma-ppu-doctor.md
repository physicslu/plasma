# PLASMA PPU Deployment Doctor — PYNQ-Z2 prototype backend

**PPU = Plasma Programming Unit.** This is a product-level **read-only diagnostic and deployment-planning tool** whose current transport/target backend is PYNQ-Z2; it is not an installer or evidence that other PPU hardware is qualified. Product-level naming and read-only safety tests are merged in [PR #1354](https://github.com/physicslu/plasma/pull/1354). Historical SWPC Path 2 [Run #42335593384](https://github.com/physicslu/plasma/actions/runs/42335593384) reported Doctor overall WARN; that observation does not qualify a deployment, FPGA Image, Site or target Flash.

## Requirements

* SWPC with Python 3.9+ and Git.
* An existing `physicslu/plasma` worktree; run the script from its root, or specify `--repo`.
* Optional: explicitly identified Z2 LAN IP/DNS name for HTTP checks.
* Optional: pinned SSH known-hosts (`~/.config/plasma/z2-login-known_hosts`) **and key-based SSH** for SSH checks. This prototype deliberately does not load the owner's private password credentials. Password-only setups will be `BLOCKED / NOT_RUN` for the optional SSH segment, not automatically classified as a failed Z2.

## Usage on SWPC

From a clean checked-out PLASMA repository, execute the source-pinned script (or the equivalent owner-authenticated Path 2 Dispatcher operation):

```sh
cd /path/to/plasma
python3 scripts/plasma_ppu.py doctor
python3 scripts/plasma_ppu.py doctor --host Z2_LAN_IP
python3 scripts/plasma_ppu.py doctor --host Z2_LAN_IP --ssh-user xilinx --json > z2-doctor-report.json
python3 scripts/plasma_ppu.py plan --route product
python3 scripts/plasma_ppu.py plan --route engineering
```

The `z2-doctor-report.json` file in this example is a **local report** created by shell redirection. Do not commit it. Avoid distributing details of your LAN addresses, Git revision, or installed release identifiers.

To use a different **already-pinned** SSH host-key file:

```sh
python3 scripts/plasma_ppu.py doctor --host Z2_LAN_IP \
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

Historical integration baseline (not the latest main): `38b4c0b68fb961b535af9e7a657f242376b9d98d` after PR #1337 (OPF Bundle v3 and Path 2 Install) merged. Worktree synchronization is independent of whether the deployed Z2 has been updated. The source references are `AGENTS.md`, `docs/deployment/ppu-deployment-start-here.md`, `docs/deployment/ppu-bootstrap-factory-and-hil.md`, and `docs/development/ppu-deploy-engineering-modules.md`. The integration-host default `plasmactl deploy` must **not** be mistaken for a Z2 install. The product route uses Bootstrap/Console, and the engineering route uses the separately reviewed `scripts/ppu-deploy` SSH transaction.

## Host-only tests

```sh
python3 -m unittest -q /path/to/test_plasma_ppu.py
```

The tests are mocks; they do not access a PYNQ-Z2. The output schema is `plasma.ppu.readonly-doctor.v0`, and the CLI intentionally has no compatibility alias under `plasma_z2.py`. CI and mocks do not qualify physical HIL; PR #1354 naming changes are already merged.

## Current supported paths

- Read-only PPU Doctor: `scripts/plasma_ppu.py`. Its `deploy` subcommand remains disabled by design.
- Site 2 current Active Set read-only checkpoint: `scripts/plasma_site2_active_readonly_path2.py`; this uses the installed, verified `ppu_asset_set.read_active()` observer and the existing paired-host/preflight/Engine identity guards. It does not receive, install, activate, reload FPGA, or flash a DUT.
- Canonical owner-authorized PPU programming and Bundle v3 B1/B2/B3: `scripts/plasma_program.py`. The Bootstrap Coordinator, PPU Lease, C-3 Session/Root, FPGA Owner/Reload and SAFE_OFF/SEALED/Recovery controls remain unchanged. Outcome-unknown transactions must be reconciled, never blindly resubmitted.
- Offline reusable Profile-only Bundle v3 builder: `scripts/opf_platform_bundle_v3_build.py` (not a deployment tool).

## Historical #1337 / #1338 Gen7 joint acceptance — retired executable entrypoints

The former Gen7-only `scripts/opf_site2_joint_acceptance.py` and `scripts/opf_site2_path2_bundle_deploy.py` were temporary Site 2 migration helpers. They read a hard-pinned Gen7 Active Set and could invoke an additional B1/B2/B3 route. After canonical `plasma_program.py` and the Site 2 Bundle A/B physical PASS, these two legacy CLI entrypoints are retired in the separately approved S2/S3/S5 deletion work. **Do not dispatch either retired script or treat a historical Work Order as authorization.**

Historical evidence: [Issue #981](https://github.com/physicslu/plasma/issues/981), [PR #1337](https://github.com/physicslu/plasma/pull/1337), [PR #1338](https://github.com/physicslu/plasma/pull/1338), and [Site 2 A/B new-path Flash/Readback/SAFE_OFF evidence](../evidence/opf-site2-ab-newpath-2026-11-08.md). The first #1337 [dispatch Run #42338239043](https://github.com/physicslu/plasma/actions/runs/42338239043) was denied before hardware execution; it is not evidence of a failed B3. Static file-set observation alone never establishes a live Flash PASS.

The retired Gen7 regression suites are replaced where relevant by Host-only Active observer safety tests, PPU Doctor tests and the retained generic Bundle v3, programming CLI and C-3/Recovery regression tests. **No change to the running Z2 is implied by source-only retirement.**
