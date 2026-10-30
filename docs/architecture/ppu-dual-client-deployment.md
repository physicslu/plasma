# PLASMA Deployment Clients and PPU Execution Boundary

Status: **Owner-approved architecture decision, 2026-10-30; implementation and production qualification pending.** This document specifies the target deployment architecture, not a claim that the current runtime supports production generic-package installation.

## Decision: two operating modes, one deployment engine

| Boundary | Engineering mode | Production mode |
| --- | --- | --- |
| Operator workstation | SWPC (development workstation) | User PC (customer workstation) |
| User interface | CLI / authorized Codex tooling | User PC-installed PLASMA Web Console |
| Transport | HTTPS to PPU Bootstrap/Deployment API | **The same** HTTPS API |
| Execution authority | PPU Linux PS | PPU Linux PS |
| Installer / transaction | **One** PPU DeploymentCoordinator | **The same** PPU DeploymentCoordinator |
| FPGA | PPU PL; eight programming Sites | PPU PL; eight programming Sites |

SWPC is a development convenience, **not** a production runtime dependency. No central management server is required for the baseline product. A User PC may manage multiple PPUs; each PPU must own its local programming, deployment transaction and recovery independently. The browser/UI is not the privileged installer and must not execute arbitrary PPU shell commands or require SSH for product deployment.

This decision concerns **deployment clients**. It does not automatically change the existing programming Web/Controller/BFF runtime boundary stated in `AGENTS.md`; any change to that normative boundary must be reconciled explicitly with the relevant runtime architecture, contracts and tests before merge. A User PC-hosted Web Console must not make SWPC a hidden production dependency.

## Shared package and API contract

Engineering CLI and production Web Console are distinct clients of one PPU API contract. Both use the same upload/chunk/commit, immutable package identity, target compatibility checks, transaction ID, staging, deployment lock, journal, verification, rollback and receipt queries. Supported artifact classes may include native C, Python and paired FPGA image/metadata, but **package kind is not authorization**. The PPU independently authenticates the principal and validates permissions, trusted publisher/provenance, target profile and permitted purpose. A caller-supplied `engineering` flag, client application name, manifest claim or SHA-256 alone grants no privilege.

Engineering diagnostic/experimental packages require an explicit PPU-validated authorization policy. Production clients cannot escalate by impersonating SWPC. All clients use the same safety and recovery invariants. Preserve the existing qualified runtime tar.gz kit contract; the generic `plasma.ppu.package.v1` ZIP must not be routed into the legacy kit installer merely by removing fail-closed guards.

## Deployment lifecycle and eight-Site exclusion

1. Authorized client selects target PPU/package, uploads and commits the package. Verification and safe staging may occur while programming continues **only** if resource isolation is demonstrated.
2. PPU validates authenticated deployment authority and exact package/target compatibility.
3. Before any activation or installation that can affect execution, the PPU scheduler atomically blocks new programming admissions, drains active jobs, confirms all eight Sites idle, no active job and hardware quiescence. A status snapshot followed by a separate lock is not atomic.
4. The existing PPU DeploymentCoordinator acquires its single transaction lock, installs/activates using bounded trusted operations, verifies the installed version and emits an evidence-backed receipt. FPGA image staging is not equivalent to FPGA Manager load.
5. On success, release the admission fence only after verification and safe readiness. On failure or unknown outcome, execute bounded rollback/recovery and keep programming blocked in `RECOVERY_REQUIRED` until safe state is proven.

Invariant: `DeployAllowed = AdmissionBlocked AND AllEightSitesIdle AND NoActiveJob AND HardwareQuiescent AND DeploymentAuthorized`.

PPU must safely complete or recover a transaction if the User PC, SWPC or network disconnects. Root Guard, FPGA ownership, image/Manifest/ABI compatibility and Golden recovery remain independent mandatory safety boundaries; do not introduce a second installer, deployment daemon, SSH transport, lock or journal.

## Ownership and implementation handoff

**Documentation owner (Path 1):** this architecture decision and documentation cross-references only.

**Implementation owner (Path 3 Codex, PR #1214):** adapt the existing `scripts/ppu-bootstrap-service.py`, `scripts/ppu-bootstrap-deployment.py`, `scripts/ppu_unified_deployment.py`, `scripts/ppu_deploy_api.py` and relevant tests as needed. Demonstrate common API semantics for SWPC CLI and future User PC clients; no hard SWPC path/identity dependency; server-side identity/purpose authorization; rejection of forged engineering privilege; atomic eight-Site admission exclusion; transaction/rollback behavior. Host-only mocks do not qualify real PS/PL or hardware.

**Gate:** PR #1214 stays Draft; no merge, SWPC/PPU/Z2 deployment, FPGA load or DUT operation without separately applicable approval and evidence. Preserve fail-closed production paths until qualified. Existing programming-runtime architecture changes are out of this documentation-only change.
