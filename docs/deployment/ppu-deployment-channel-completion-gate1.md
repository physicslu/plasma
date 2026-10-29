# SWPC → PPU Deployment Channel Completion — Gate 1 / Path 1

Status: **implementation work order / NOT an implementation or live qualification**. Owner decision 2026-10-29. Supersedes the earlier priority to build Capability Bundle v2 / Exact ICPN Resolver first.

## Goal and source of truth

Deliver the smallest authentic, reusable SWPC-to-PPU deployment path for generic `native-c`, `python` and `fpga-image` packages using the **existing** Bootstrap `POST /v1/deployments`, upload/status API, existing `DeploymentCoordinator`, `deployment.lock`, and `deployment.json`. No new coordinator, installer adapter, daemon, journal, or parallel SSH deployment channel. Source contracts: `AGENTS.md`, the applicable detailed development/deployment clauses, `docs/architecture/ppu-unified-deployment-gate1.md`, merged #1209 and #1213.

The first acceptance is a **real PS test application delivery and verifiable installation receipt**, followed by an FPGA Image + companion Manifest/HWH delivery and installation receipt. FPGA Manager *load* and DUT activity are separate, explicitly authorized hardware acceptance; package verification does not imply a loaded image or qualified programmer.

## Verified starting point and blockers

| Area | Current evidence in main | Remaining work |
| --- | --- | --- |
| SWPC transport | `scripts/ppu_deploy_api.py` provides HTTPS-only mock-tested upload/chunk/commit/status; `submit()` rejects `engineering-module` and `fpga-image` before network | Admit new kinds only after authenticated PPU server-side policy, trusted provenance and actual installer authority exist; integrate real CLI |
| Package contract | `scripts/ppu_unified_deployment.py` verifies Host-only `plasma.ppu.package.v1` ZIP kinds `native-c`, `python`, `fpga-image`, strict hashes and FPGA image/HWH pairing | Wire immutable, verified package identity into real deployment transaction without treating `install_qualified=False` as authority |
| Engine | Existing `DeploymentCoordinator.execute_package_host_only()` stages and rolls back only in sandbox | Extend the **same** transaction engine to approved target staging, atomic activation, receipts and bounded recovery |
| Bootstrap API | Existing runtime endpoint and upload protocol; Engineering/FPGA network writes intentionally blocked | Server-side request admission, Principal/Master generation, publisher/source authorization and end-to-end correlation |
| PPU security | Protected FPGA Root Entry, Image+Manifest validation, owner/lease, Golden recovery exist in separate hardware workflow | Integrate verified staging without granting untrusted package direct Root, FPGA Manager or arbitrary path access |
| Cross-host | Host-only mock responses; engineering SSH installer still present | Authenticate real TLS endpoint, ensure idempotent receipts and unknown-outcome reconciliation; retire SSH only after parity |
| Hardware | No actual SWPC/Z2/FPGA/DUT acceptance for unified API | Separate Path 3 scope and observed PASS/FAIL/NOT_RUN evidence |

## Engineering sequence

1. **Inventory and contract test:** pin latest `main` and exact existing Bootstrap request, upload, journal, installer and Root boundaries. Write a Host-only SWPC client → in-process Bootstrap API → one Engine test with an immutable package, committed upload and correlated transaction ID. Keep current network denial until server admission is complete.
2. **Trusted PS installation:** add a bounded, independently authorized target install inside the existing Engine. Validate source, package hash, exact target profile, allowed paths, executable privileges, owner generation, atomic release activation and compensation. No arbitrary command or Master-controlled Root Python.
3. **FPGA delivery without load:** accept paired Image/HWH and protected image Manifest through the same upload/transaction path. Verify board/FPGA part, ABI and hash; stage without touching FPGA Manager or Golden. Hardware quiescence and protected Root load are **not** inferred from delivery.
4. **Transport and recovery:** TLS peer validation, server-side Master/publisher policy, upload limits, no redirect/token leak, no silent retries on unknown outcomes, reboot/timeout/partial upload/repeated request tests, version and receipt query.
5. **CI and handoff:** GitHub-hosted positive and negative tests for C, Python, FPGA and cross-kind denial; provide pinned HEAD, CI, evidence, remaining hardware prerequisites and Gate 2 readiness in a separate implementation Draft PR.

## Explicit negative cases

Reject unknown/revoked Principal, unauthorized purpose, untrusted publisher, mismatched source pin/board/FPGA part/ABI, wrong SHA or file size, ZIP traversal/symlink/duplicate entry, unexpected executable, payload type crossover, FPGA Image missing matching metadata, unsupported installer path, concurrent deployment or active Site owner, lost upload receipt, crash between stage and activation, corrupted cached release and ambiguous recovery. Never infer successful installation from a completed upload.

## Stage gates and acceptance

**Path 1 Gate 1**: code and GitHub-hosted CI only; independent Draft PR, no merge, deployment, SWPC/Z2/DUT operation, FPGA load or production claim. Documentation of this work order alone does not satisfy Gate 1.

**Path 3 real acceptance (later, explicitly scoped)**: SWPC transfers a harmless test C/Python app to an enrolled PPU; verify installation hash, version, execution under bounded non-root identity, rollback and recovery. Then transfer a compatible FPGA Image/HWH/Manifest, verify installed bytes and identity **without loading PL**. Only a separately scoped, protected Root hardware operation may prove FPGA Manager load, with owner lock, known boot identity and safe recovery. Capture observed evidence; label anything else NOT_RUN.

**Deferred**: Capability Bundle v2, Exact ICPN Resolver, mixed eight-Site scheduling, production L2 qualification, automatic FPGA selection, and partial reconfiguration.
