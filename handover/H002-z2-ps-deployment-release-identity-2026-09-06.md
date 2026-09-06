# H002 — PYNQ-Z2 PS Deployment, Managed Loopback, and Release Identity

**Date:** 2026-09-06  
**Project:** Plasma Universal Multi-Site IC Programmer  
**Repository:** `physicslu/plasma`  
**Main at handover creation:** `d30f64ae70ff123c4c1915d12b24a5613328e41f`  
**Active implementation PR:** [#382 — Release: qualify deployment identity and accept PS-only zero-Site topology](https://github.com/physicslu/plasma/pull/382)  
**PR branch at handover creation:** `agent/release-identity-v2-ps-zero-sites`  
**PR head at handover creation:** `6c0ccc121aca11451e2bc28bc857744909d51df0`  
**Status:** Real PYNQ-Z2 PS-only deployment evidence exists; Managed PS Loopback is still blocked pending PR #382 completion and post-merge exact-SHA requalification  
**PS-to-PL admission:** NO  
**Real IC programming admission:** NO  
**8-Site hardware qualification:** NO

## 1. Purpose

This handover transfers the current Plasma deployment / qualification workstream to a new engineering session without relying on chat history.

It covers:

1. the real PYNQ-Z2 PS-only deployment already performed;
2. the macOS Control Station deployment used to reach that Z2;
3. the Manager fleet-contract defect exposed by the real board;
4. the release-provenance defect exposed by repeated `0.1.0` installer builds;
5. PR #382, which proposes the software fixes;
6. the exact continuation required before Managed PS Loopback may be claimed.

Authority order for continuation is:

```text
AGENTS.md / current executable repository state
    > exact-SHA build and installation evidence
    > checked-in handover snapshot
    > chat recollection or inferred state
```

If this document conflicts with newer code, tests, `AGENTS.md`, or current CI, the newer repository state is authoritative.

## 2. Product architecture boundary

Plasma is a multi-Site IC programming system:

```text
Plasma System
└── Facility
    └── PPU (Plasma Programming Unit)
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Current product direction:

- Embedded Linux is the PPU control processor / PS software node.
- FPGA PL provides custom programming peripherals and timing-sensitive hardware.
- One PPU is intended to support 8 simultaneous programming Sites.
- The Control Station communicates with PPUs over Ethernet.
- Canonical Site identity is one-based. There is no `SITE 0`.

For the qualification described here, the hardware boundary is deliberately closed:

```text
sites: []
loads_fpga: false
accesses_pl: false
changes_target_power: false
programs_real_ic: false
```

Therefore this handover is about **PS software deployment and network/control-plane qualification**, not PL, electrical, fixture, target-power, or IC-programming qualification.

## 3. Repository governance

`AGENTS.md` defines the exact two-gate model:

```text
read-only inspection
    -> Gate 1 plan approval
    -> autonomous implementation / tests / commits / PR / CI repair
    -> Gate 2 merge approval
    -> merge
```

Important operational rules:

- Gate 1 is required before code/config/test/doc/branch/PR/deployment mutations.
- After Gate 1, implementation and CI repair proceed autonomously.
- Gate 2 is requested only when the PR is genuinely merge-ready.
- CI cannot prove PYNQ-Z2 HIL, PS-to-PL, electrical behavior, or real IC programming.
- A post-merge deployment/HIL step that was already included in the approved Gate 1 scope does not create a third gate.

PR #382 has Gate 1 approval. It does **not** yet have Gate 2 approval.

## 4. Evidence ladder used in this workstream

The practical evidence ladder is:

```text
L0  Static / Contract
L1  Unit / Regression
L2  Packaged ARMv7
L3  Linux Integration
L4  Persistent Integration Host
L5  PYNQ-Z2 HIL
L6  Real Device / 8-Site Qualification
```

The real work described here reached a **real PYNQ-Z2 PS-only slice**. Do not inflate that into full PL/Site HIL or L6 qualification.

## 5. Frozen exact-SHA qualification baseline

The original real-Z2 deployment candidate was frozen at:

```text
1fc0c3ad19c7405b503ef9a5fc15377911cecbca
```

Qualification branch:

```text
qualification/z2-ps-1fc0c3ad
```

This SHA was used to build both the macOS Control Station artifact and the PPU ARMv7 artifact before real deployment.

### 5.1 Exact-SHA macOS workflow

Workflow:

```text
macOS Control Station installer acceptance
Run ID: 34017425437
HEAD:   1fc0c3ad19c7405b503ef9a5fc15377911cecbca
```

The correct `.pkg` from that run is:

```text
plasma-control-station-0.1.0-macos-arm64.pkg
SHA-256:
102a7c3e70c271478c0d298502358803f5e0149bbc731a7aa2ca7daa347b9790
```

Important correction preserved for future sessions:

- `81c7705c...` was **not** the exact-SHA package from run `34017425437`.
- The `81c7705c...` package embedded old source SHA `ea0ba1d7c3b83e8ecfd1c0d8812e0b76d42cd8b2`.
- The exact run artifact embeds `1fc0c3ad...` and hashes to `102a7c3e...`.

This incident is the concrete evidence that motivated Release Identity v2.

### 5.2 Exact-SHA PPU workflow

Workflow:

```text
PPU release artifact
Run ID: 34017598823
HEAD:   1fc0c3ad19c7405b503ef9a5fc15377911cecbca
```

The real Z2 installer later recorded the PPU release archive digest as:

```text
9bdf35d5452b95b075c92f2f2fca1052bad41750476fa6909f65bec7de85fc0d
```

Do not substitute a guessed artifact hash. Use the detached sidecar or installed evidence for any future exact claim.

## 6. Real PYNQ-Z2 baseline

Observed real board baseline before Plasma mutation:

```text
Host / board       PYNQ-Z2
OS                 PynqLinux 3.0 Carlisle / Ubuntu 22.04 base
Kernel             6.6.10-xilinx-v2024.1
Architecture       armv7l
glibc              2.35
systemd            249
System Python      3.10.4
PYNQ               3.1.1
Ethernet           192.168.2.99/24
```

PYNQ System Python ownership must remain intact.

The accepted architecture decision is:

```text
/usr/bin/python3 and the PYNQ venv are PYNQ/OS-owned.
Plasma owns an isolated interpreter below /opt/plasma/python/.
```

Do not replace `/usr/bin/python3` to satisfy Plasma.

## 7. Plasma isolated Python qualification

A native CPython build was performed once on the real Z2 to establish a trusted baseline:

```text
Python       3.11.16 final
Architecture armv7l
Executable   /opt/plasma/python/3.11.16/bin/python3
OpenSSL      OpenSSL 3.0.2
SQLite       3.37.2
Core modules PASS
```

PYNQ regression after installation remained:

```text
System Python 3.10.4
PYNQ          3.1.1
```

The native `make -j1` build took approximately 2280 seconds. That build should **not** become the normal product deployment mechanism. Long term, Plasma should distribute a compatible, immutable, CI-built ARMv7 runtime artifact. That is a separate future scope.

For the immediate post-PR-#382 requalification, the existing `/opt/plasma/python/3.11.16` may be reused if its integrity and PYNQ ownership state remain intact. There is no reason to rebuild it merely because the Plasma PPU release changes.

## 8. Real Z2 PS-only installation evidence

The real board installation command used the exact-SHA PPU artifact and the isolated Python:

```text
sudo python3 plasma-ppu-z2-installer.py install
  --release-artifact <exact 1fc0c3ad PPU release>
  --sidecar <matching sidecar>
  --plasma-python /opt/plasma/python/3.11.16/bin/python3
  --gateway-host 192.168.2.99
  --ppu-id z2-dev-01
  --facility-id lab
```

Installed evidence recorded:

```text
result          PASS
product_version 0.1.0
git_sha         1fc0c3ad19c7405b503ef9a5fc15377911cecbca
release_id      0.1.0-1fc0c3ad19c7
release_root    /opt/plasma/releases/0.1.0-1fc0c3ad19c7
current         /opt/plasma/current
plasma_python   3.11.16 final / armv7l
gateway_host    192.168.2.99
```

Hardware boundary in the installer evidence:

```text
loads_fpga          false
accesses_pl          false
changes_target_power false
programs_real_ic     false
```

Post-install state:

```text
plasma-server.service enabled / active
plasma-web.service    enabled / active
Gateway readiness     PASS
execution             ready
ppu_id                z2-dev-01
PYNQ Python/PYNQ      preserved
```

Mac direct request to the real Z2 Gateway also passed:

```text
http://192.168.2.99:18080/api/health/ready
```

Therefore the exact-SHA **Z2 PS software installation** was proven. Managed PS Loopback was not yet proven.

## 9. Real macOS Control Station installation evidence

The correct exact-SHA `.pkg` was cleanly installed after removing the older pilot package.

Installed `macos-installer.json` reported:

```text
product_version 0.1.0
platform        macos
architecture    arm64
git_sha         1fc0c3ad19c7405b503ef9a5fc15377911cecbca
```

Manager health passed:

```json
{"ok": true, "service": "plasma-manager", "contract_version": "1", "manager": "alive"}
```

The Console root returned an HTTP redirect when tested without redirect following. This is not itself a failure; the browser/HTTP client follows the redirect.

The operator then opened the real Console and enrolled:

```text
alias    z2
endpoint http://192.168.2.99:18080
lifecycle pending
```

The stored endpoint was machine-verified as exactly:

```text
http://192.168.2.99:18080
```

## 10. Real Manager observation and the blocker found on hardware

The Manager successfully reached the real Z2 and reported:

```text
gateway_live        true
execution_ready     true
transport_state     reachable
execution_state     ready
identity_conflict   false
```

But it rejected the fleet contract:

```text
contract_compatible false
ppu                 null
sites               []
error:
/api/node ppu.site_count must be a positive integer
```

The Console therefore correctly remained fail-closed:

```text
PPU Registry: z2
Lifecycle:    Pending
Execution:    ready
PPU ID:       Awaiting probe
Observation:  unknown
Sites:        —
```

This is a useful distinction:

```text
Console -> Manager              PASS
Manager -> Z2 transport         PASS
Z2 Gateway                      PASS
Z2 execution readiness          PASS
Fleet identity/topology trust   FAIL
Commissioning                   BLOCKED
Managed PS Loopback             BLOCKED
```

## 11. Root cause: zero configured Sites versus capacity

The Z2 installer deliberately writes:

```yaml
server:
  max_supported_sites: 8

sites: []
```

That means:

```text
max_supported_sites = hardware/product capacity ceiling
site_count           = currently configured topology
site_count = 0       = legal PS-only closed-hardware state
enabled_site_count   = 0
sites                = []
```

The old Manager validator instead required:

```text
site_count >= 1
```

This was the contract defect.

The correct invariant is:

```text
site_count >= 0
0 <= enabled_site_count <= site_count
len(status.sites) == site_count
```

If any Site exists, its canonical identity still obeys:

```text
site_id >= 1
```

Allowing **zero Sites** is not the same as allowing **Site 0**.

Do not work around this defect by fabricating 8 Sites. That would falsely convert a capacity declaration into an observed/configured hardware-topology claim.

## 12. Release identity defect exposed by the deployment

The old macOS packaging model used only product version for multiple identity surfaces:

```text
plasma-control-station-0.1.0-macos-arm64.pkg
/Library/Application Support/Plasma/releases/0.1.0
package version 0.1.0
```

Different source commits could therefore produce different bytes under the same visible version and filename. The real session demonstrated this with:

```text
old package source SHA  ea0ba1d7...
new package source SHA  1fc0c3ad...
visible product version 0.1.0 for both
same .pkg filename      yes
```

This is a deployment traceability defect, not a cosmetic naming problem.

The intended Release Identity v2 model is:

```text
product_version = SemVer product lineage
release_id      = <product_version>-<git-sha-prefix12>
artifact_digest = SHA-256 of exact bytes
```

These serve different purposes and must not be collapsed into one field.

Example:

```text
Product Version 0.1.1
Git SHA         abcdef1234567890...
Release ID      0.1.1-abcdef123456
Artifact SHA256 <64 hex>
```

## 13. PR #382 scope

PR #382 was opened to close both deployment defects found above.

Current proposed product version:

```text
0.1.1
```

Current scope includes:

1. Manager accepts legal PS-only `site_count=0` topology.
2. `max_supported_sites` remains capacity, not configured count.
3. Any actual Site remains one-based.
4. Common Release Format artifact names include Git SHA prefix.
5. macOS `.pkg` names and installed immutable release directories include release identity.
6. Windows `.msi` names and Program Files release directories include release identity.
7. PPU ARMv7 release archives include release identity.
8. Z2 installer transport names include release identity.
9. GitHub Actions artifact names include release identity.
10. Persistent integration release lookup follows the new naming.
11. Regression tests prove same SemVer / different source SHA cannot reuse the same deployable filename.

The PR explicitly does **not** claim new real-Z2 HIL evidence. Real deployment must be repeated after merge against the exact post-merge SHA.

## 14. PR #382 CI state at handover creation

PR head when this handover was created:

```text
6c0ccc121aca11451e2bc28bc857744909d51df0
```

GitHub reported the PR as mergeable at the time of inspection, but it is not merge-ready because one required engineering workflow is failing and the branch also needs final current-main alignment/audit before Gate 2.

Completed PR workflow state:

| Workflow | Run | Result |
|---|---:|---|
| Product release format acceptance | 34027836682 | PASS |
| Repository contracts | 34027836700 | PASS |
| Mock CD | 34027836684 | PASS |
| macOS Control Station installer acceptance | 34027836679 | PASS |
| Mock CD Browser Runtime Acceptance | 34027836681 | PASS |
| Python and PL source tests | 34027836673 | PASS |
| Control Station runtime packaging acceptance | 34027836695 | PASS |
| Windows Control Station installer acceptance | 34027836714 | PASS |
| PPU release artifact | 34027836678 | **FAIL** |

### 14.1 What passed inside the failing PPU workflow

The failure is **not** evidence of an ARMv7 runtime break.

Before the failing step, the following passed:

```text
Python 3.10 Z2 installer bootstrap compatibility PASS
PPU packaging regression tests              PASS
94 focused tests                            PASS
PPU runtime build/validate                  PASS
SHA-qualified PPU release construction      PASS
clean release verification                  PASS
closed hardware-boundary verification       PASS
detached SHA-256 sidecar                    PASS
Z2 installer independent release verify     PASS
ARMv7 userspace execution under QEMU        PASS
PS loopback inside ARMv7 userspace          PASS
```

The PR CI release was produced as:

```text
plasma-ppu-0.1.1-d27a7aed3a68-linux-armv7l.tar.gz
```

with archive SHA-256:

```text
bd03a1e5c1fce5d1f6619696c58ffc4c0cc834b75d4f2d72c4568f37cac17615
```

Important: `d27a7aed...` is the GitHub PR **synthetic merge ref SHA**, not the source branch head and not a post-merge `main` deployment candidate. PR artifacts remain validation evidence only.

### 14.2 Exact PPU CI failure

The failing step was:

```text
Run one-command PPU Network Phase 1 acceptance
```

Error:

```text
ppu-network-phase1-acceptance:
canonical PPU release was not produced under .../plasma-ppu-network-phase1/release
```

Root cause is confirmed in `scripts/ppu-network-phase1-acceptance.py` on the PR branch. The harness still looks for the old filename:

```text
plasma-ppu-<version>-linux-armv7l.tar.gz
```

while `scripts/ppu-release.py` now emits:

```text
plasma-ppu-<version>-<sha12>-linux-armv7l.tar.gz
```

This is an incomplete Release Identity v2 propagation defect in the acceptance harness.

Do not rerun the workflow unchanged and call it transient. The log gives deterministic code-level evidence of the mismatch.

## 15. Main moved while PR #382 was in progress

Current `main` at handover creation is:

```text
d30f64ae70ff123c4c1915d12b24a5613328e41f
Merge pull request #381
IC Support: derive memory geometry relationships deterministically
```

PR #382 was originally based before that merge. Before Gate 2, the implementation branch must be reconciled with the latest `main`, then CI/diff/review state rechecked.

Do not assume an earlier green run is sufficient after branch reconciliation.

## 16. Known issues that must not be mixed together

### 16.1 PPU Network Phase-1 stale filename

Current blocking PR #382 defect:

```text
ppu-network-phase1-acceptance.py
still assumes old non-SHA-qualified PPU filename
```

Fix this within the already approved PR #382 Gate 1 scope and search related Phase-2 / network / persistent harnesses for the same stale naming assumption.

### 16.2 macOS first-attempt LaunchAgent bootstrap EIO

During the earlier real Mac installation, one attempt failed with a LaunchAgent bootstrap `Input/output error`; an immediate later installation succeeded and both services ran.

Treat this as a separate installer robustness candidate, likely around bootout/bootstrap timing or retry behavior. Do not silently mix a broad launchd robustness redesign into the narrow PR #382 release-identity / zero-Site fix unless required for current acceptance.

### 16.3 Persistent-host runtime-version parity gap

A previously known unrelated repository defect remains: the persistent integration readiness checker does not fully enforce parity with the cloud setup baseline for Python >=3.11 and Node >=22.13.

That issue is not the blocker for this Z2 Managed PS Loopback path and should not be smuggled into PR #382.

## 17. Current proven / not-proven matrix

### Proven from the real `1fc0c3ad...` deployment

```text
Exact-SHA PPU artifact installed on real PYNQ-Z2      PASS
Isolated Plasma Python 3.11.16 final / armv7l         PASS
PYNQ System Python preserved                          PASS
PYNQ 3.1.1 preserved                                 PASS
plasma-server systemd service                         PASS
plasma-web / Gateway systemd service                  PASS
Z2-local Gateway readiness                            PASS
Mac -> real Z2 Gateway network path                   PASS
Exact-SHA macOS Control Station install               PASS
Mac Manager health                                    PASS
Console -> Manager                                    PASS
Manager -> real Z2 transport                          PASS
Manager sees Z2 execution ready                       PASS
```

### Explicitly not proven / blocked

```text
Manager fleet contract for PS-only zero-Site topology BLOCKED on old SHA
PPU commissioning                                     BLOCKED
Managed PS Loopback                                   NOT PROVEN
PS-to-PL                                              NOT PROVEN
FPGA loading/execution                                NOT PROVEN
Site I/O                                              NOT PROVEN
target power                                          NOT PROVEN
real IC programming                                   NOT PROVEN
8-Site hardware concurrency                           NOT PROVEN
production code signing/notarization                  NOT PROVEN
```

## 18. Required continuation sequence

A new session should continue in this order.

### Step 1 — Read governing state

Read:

```text
AGENTS.md
handover/H002-z2-ps-deployment-release-identity-2026-09-06.md
PR #382 current diff / comments / CI
```

Do not continue from chat memory alone.

### Step 2 — Repair PR #382 PPU naming propagation

At minimum:

```text
scripts/ppu-network-phase1-acceptance.py
```

must derive or locate the SHA-qualified PPU release identity correctly.

Then search other executable harnesses for old forms such as:

```text
plasma-ppu-$version-linux-armv7l.tar.gz
plasma-control-station-$version-...
releases/<version>
```

Do not change unrelated contracts merely because a textual old example exists in historical documentation.

### Step 3 — Re-run relevant CI

Expected outcome before Gate 2:

```text
Product Release                    PASS
macOS Installer                    PASS
Windows Installer                  PASS
Control Station Runtime            PASS
Python / PL source tests            PASS
PPU Release Artifact               PASS
no blocking review findings
```

A deterministic code failure must be fixed, not repeatedly retried as transient.

### Step 4 — Reconcile with latest `main`

Bring the PR branch current with `main`, resolve conflicts deliberately, and rerun affected CI.

### Step 5 — Final diff/review audit

Verify:

```text
product_version = 0.1.1
zero-Site PS-only semantics are explicit
Site 0 remains invalid
release_id is version + SHA12
full SHA remains in manifests
artifact SHA-256 remains separate integrity evidence
macOS / Windows / PPU identity conventions are consistent
no old filename assumptions remain in executable acceptance paths
```

### Step 6 — Gate 2

Only when merge-ready, ask for the explicit merge approval required by `AGENTS.md`.

### Step 7 — Merge and freeze the post-merge exact SHA

After Gate 2 and merge:

```text
freeze exact main SHA
```

Do not deploy a PR merge-ref artifact as the qualification candidate.

### Step 8 — Build exact post-merge deployment artifacts

Build or dispatch:

```text
macOS Control Station installer
PPU linux-armv7l release + Z2 installer kit
```

The filenames should visibly contain:

```text
0.1.1-<post-merge-sha12>
```

Retain detached SHA-256 files.

### Step 9 — Reinstall / upgrade the real Mac and Z2

Verify installed manifests report the exact same post-merge source SHA.

On Z2, reuse the qualified Plasma Python 3.11.16 if still intact; do not rebuild Python without evidence-based need.

Keep the PS-only hardware boundary:

```text
sites: []
loads_fpga=false
accesses_pl=false
changes_target_power=false
programs_real_ic=false
```

### Step 10 — Manager enrollment and zero-Site trust check

Enroll or update:

```text
alias:    z2
endpoint: http://192.168.2.99:18080
```

Expected trusted observation after PR #382 fix:

```text
gateway_live        true
execution_ready     true
contract_compatible true
identity_conflict   false
ppu.ppu_id          z2-dev-01
ppu.site_count      0
ppu.enabled_site_count 0
sites               []
errors              []
```

Only then commission the entry.

### Step 11 — Select z2 and run canonical Managed PS Loopback

Canonical acceptance command from the exact post-merge repository checkout:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://127.0.0.1:18000/api/manager/ppu \
  --environment managed-z2-ps
```

Only a PASS here supports the claim:

```text
Managed PS Loopback PASS
```

### Step 12 — Record exact-SHA evidence

Retain at minimum:

```text
post-merge Git SHA
product_version
release_id
macOS .pkg SHA-256
PPU archive SHA-256
installed macOS manifest
installed Z2 last-install evidence
Manager fleet observation
Managed PS Loopback acceptance output
PYNQ ownership regression output
```

## 19. What the next session must not do

Do not:

- create fake Sites merely to make Manager green;
- reinterpret capacity 8 as configured Site count 8;
- claim Site 0 exists;
- deploy PR synthetic merge-ref artifacts as production qualification candidates;
- rely on filename alone for artifact provenance;
- replace PYNQ System Python;
- claim PL/FPGA/electrical/real-IC evidence from PS-only tests;
- treat a deterministic CI filename mismatch as transient;
- mix unrelated persistent-runner or launchd robustness changes into PR #382 without scope justification;
- request Gate 2 before all blocking CI/review/mergeability conditions are satisfied.

## 20. Recommended continuation prompt

A new session can start with:

```text
Read AGENTS.md and handover H002. Continue PR #382 from the documented PPU Network Phase-1 Release Identity v2 filename failure. Repair the remaining SHA-qualified artifact-name propagation, run CI to merge-ready, then follow the two-gate process. Do not claim Managed PS Loopback until exact post-merge Mac + Z2 deployment and the canonical ps-loopback acceptance pass on the real PYNQ-Z2.
```

That is the authoritative continuation point for this handover.
