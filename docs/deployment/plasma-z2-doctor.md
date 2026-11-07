# PLASMA Z2 Deployment Doctor — safe standalone prototype

This is a **read-only diagnostic and deployment-planning tool**, not a Z2 installer. It is staged in a Draft PR for `physicslu/plasma`, has not run on the owner's SWPC/Z2, and therefore **does not qualify** any deployment, FPGA Image, Site or target Flash behavior.

## Requirements

* SWPC with Python 3.9+ and Git.
* An existing `physicslu/plasma` worktree; run the script from its root, or specify `--repo`.
* Optional: explicitly identified Z2 LAN IP/DNS name for HTTP checks.
* Optional: pinned SSH known-hosts (`~/.config/plasma/z2-login-known_hosts`) **and key-based SSH** for SSH checks. This prototype deliberately does not load the owner's private password credentials. Password-only setups will be `BLOCKED / NOT_RUN` for the optional SSH segment, not automatically classified as a failed Z2.

## Usage on SWPC

Copy `plasma_z2.py` outside the repository (for example into a separate tools directory), then:

```sh
cd /path/to/plasma
python3 /path/to/plasma_z2.py doctor
python3 /path/to/plasma_z2.py doctor --host Z2_LAN_IP
python3 /path/to/plasma_z2.py doctor --host Z2_LAN_IP --ssh-user xilinx --json > z2-doctor-report.json
python3 /path/to/plasma_z2.py plan --route product
python3 /path/to/plasma_z2.py plan --route engineering
```

The `z2-doctor-report.json` file in this example is a **local report** created by shell redirection. Do not commit it. Avoid distributing details of your LAN addresses, Git revision, or installed release identifiers.

To use a different **already-pinned** SSH host-key file:

```sh
python3 /path/to/plasma_z2.py doctor --host Z2_LAN_IP \
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

Known current architecture in `main` at inspection on 2026-11-07: `68536c66bb82be3f9cc93618c7957ea3f9c1a1e2`. The source references are `AGENTS.md`, `docs/deployment/ppu-deployment-start-here.md`, `docs/deployment/ppu-bootstrap-factory-and-hil.md`, and `docs/development/ppu-deploy-engineering-modules.md`. The integration-host default `plasmactl deploy` must **not** be mistaken for a Z2 install. The product route uses Bootstrap/Console, and the engineering route uses the separately reviewed `scripts/ppu-deploy` SSH transaction.

## Host-only tests

```sh
python3 -m unittest -q /path/to/test_plasma_z2.py
```

The tests are mocks; they do not access a PYNQ-Z2. Neither this prototype nor these tests constitute a Gate 2 merge or physical HIL approval.

## Next implementation gate

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
