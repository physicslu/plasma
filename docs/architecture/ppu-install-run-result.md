# PLASMA PPU — Install → Run → Result (single-appliance lifecycle)

**Owner decision: 2026-11-03, revised after PR #1278 opened.** This is the **target product/operator contract** for one embedded-Linux + FPGA PPU. It retires **B4** as an independent Bundle deployment stage. It does **not** claim the new B3 behavior is already implemented or Z2 HIL qualified. Executable code, wire contracts, tests and receipts take precedence over prose ([AGENTS.md](../../AGENTS.md)).

## Operator-visible workflow

| Operation | Meaning | Internal implementation |
| --- | --- | --- |
| **Install Bundle** | Receive, admit, install and verify a complete Bundle; **on successful completion select it as the one Active Asset Set**; if the Bundle contains an FPGA Image, **load it by default under explicit operation authorization** | **B1** Receive → **B2** Admission → **B3** Install/Verify + internal Active Set commit and, when applicable, guarded FPGA load |
| **Run Job** | Execute a specifically authorized Job against the selected Set and qualified Site | Runtime trigger → **C-1** Job lease/authorization → **C-2** non-root Package executor → **C-3** restricted Site Worker / adapter |
| **Get Result** | Read Job status, receipt, execution logs and actual hardware evidence | Existing Runtime, journal and receipt; no second result engine |

B1/B2/B3 and C-1/C-2/C-3 are **internal components**, not six operator actions. No standalone B4 button, B4 public API, activation service, second Job engine, second FPGA loader or broker framework is required.

## Stage B: target B3 success contract

**A successful Install means a verified new Active Set**, not merely files staged on disk. Staging is an internal preparatory state; a failed, denied or uncertain transaction must never be reported as a successful Install.

1. **B1 Receive** commits the selected Bundle bytes. **B2 Admission** verifies source, ZIP/file hashes, device/target and the applicable authorization. Neither alone installs, activates, configures FPGA or executes a Job.
2. **B3 Install/Verify** stages and re-verifies the complete immutable Set, exact canonical Bundle ZIP SHA256 and dependencies. It obtains an authoritative PPU/Job quiescence lease and checks for conflicting hardware owners before changing live configuration.
3. **If an FPGA Image Package is present:** the normal Install operation **requests FPGA loading by default**, using the existing protected Root path, a fresh explicit **FPGA-load-capable owner authorization**, Golden/current-boot/ownership preconditions and actual Image/ABI Identity PASS. **Only then** atomically publish the new `assets/active.json` Set identity and return Install success. No second user action is needed.
4. **If no FPGA Image Package is present:** B3 still atomically selects the newly verified Set as Active after the same relevant quiescence/identity checks. **Do not load or reconfigure FPGA** just to activate a Python/native-C/Profile/Catalog-only Set. The currently loaded FPGA remains under its own identity/ABI qualification; the next Job must check exact compatibility and fail closed if mismatched.
5. **On denial/failure/uncertainty:** do not publish a new Active Set or report Install success. If the FPGA was already changed but the pointer update or validation fails, the physical configuration is not automatically reversible; record `recovery_required` / `NOT_READY` as applicable, block Job execution, preserve protected evidence and use existing guarded recovery. Never silently assume the old Active Set is ready.
6. **On concurrent Jobs:** no Set switch or FPGA load may race with a running, queued or cancelling Job or an unaccounted-for MMIO/OpenOCD hardware owner.

**Wire/API boundary:** the existing request explicitly carries `fpga_load: true|false` and an operation-specific owner authorization. **“Load by default” is a product/UI/orchestrator default**, not permission for a server to infer a privileged operation from an omitted field or from a lesser `bundle.install` authorization. For a Bundle containing an FPGA Image, the ordinary Install caller must construct an explicit `fpga_load:true` request with the appropriate authorization. Any exceptional install-only/staging mode must be separate and must **not** report the target operator-level Install as successfully Active. Changing the current API or CLI behavior requires a separately approved implementation Gate.

**No-FPGA activation gap:** the old B3 `fpga_load:false` path stages only. Under the revised target, a verified Bundle containing no FPGA Image must instead become Active after B3 without FPGA reconfiguration. The code/receipt/CI migration remains **NOT_IMPLEMENTED** until independently evidenced; do not claim the documentation change provides this capability.

## Stage B: current implementation baseline (not target-compliant yet)

- Current B3 `fpga_load:false`: verified staging only, **no Active pointer switch**. `B3_INSTALL_QUEUED` is not `ACTIVE` or `READY`.
- Current B3 with explicitly requested/authorized `fpga_load:true` and a qualifying FPGA Image: guarded Root FPGA load; after Image Identity PASS the Coordinator can publish the selected Active pointer.
- The current wire request does **not** implicitly default missing `fpga_load` to true. Root Guard, current-boot pin, quiescence, Site Admission, Golden and error journal behavior are not relaxed by this design decision.
- For both paths, `ACTIVE` still does **not** prove a programming Job is `READY`, nor that FPGA/DUT Flash E/P/V/R occurred.

**Retired terminology:** Historical docs, evidence, code/receipt fields can still mention `B4`, `b4_activate` or `activate_staged_asset_set`. They denote historical proposals or **internal** atomic Set selection/recovery, not an independent operator stage. Do not rewrite retained evidence or remove safety functions merely to erase the old label.

## Stage C: current integration boundary

- **C-1:** authoritative PPU-exclusive Package Action lease, Site resource declaration, Runtime quiescence and authorization.
- **C-2:** controlled Python/native-C Package lifecycle, dedicated-UID integration design, timeout/cancel, journal and receipt.
- **C-3:** local Site Worker with a restricted Hardware Adapter. The present ABI-v5 adapter is **Site 1/2 `probe` only**, not Package-driven Flash Erase/Program/Verify.
- Stage C production integration is present in source, but the formal `plasma-server` Runtime trigger/caller and Z2 deployment/qualification are separate outstanding tasks. Eight-Site concurrent execution is not qualified.

## Result, rollout and non-goals

Result evidence must bind Job, Site, target IC, selected Set/Package identity, operation, completion state and authentic receipts/errors. Staged, `ACTIVE`, `READY`, Host-only PASS and `AUTHORIZED_NOT_EXECUTED` are not target Flash-programming PASS.

The operator workflow is **Install → Run → Result**. This is a documentation-level owner architecture decision; implementing the **B3 auto-activate + default authorized FPGA load** behavior, updating callers/receipt expectations, Host-only regression, Gate 2 merge and Z2 HIL each require their own actual evidence and approval. No deployment, FPGA reconfiguration or DUT operation is authorized by this text.
