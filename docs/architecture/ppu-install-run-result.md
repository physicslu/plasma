# PLASMA PPU — Install → Run → Result (single-appliance lifecycle)

**Owner decision: 2026-11-03.** This is the **target product/operator workflow** for one embedded-Linux + FPGA PPU. It replaces the proposal to expose **B4** as an independent Bundle deployment stage. It does **not** declare an unimplemented path or Z2 HIL qualified. Code, wire contracts, tests and actual receipts take precedence over descriptive prose ([AGENTS.md](../../AGENTS.md)).

## Operator-visible workflow

| Operation | Meaning | Internal implementation |
| --- | --- | --- |
| **Install Bundle** | Receive an explicitly selected complete Bundle v3, verify provenance/target/content, install the immutable Set, and perform any separately authorized in-transaction Set selection / FPGA load | **B1** Receive → **B2** Admission → **B3** Install/Verify |
| **Run Job** | Execute a specifically authorized Job against the exact selected Set and qualified Site | Runtime trigger → **C-1** Job lease/authorization → **C-2** non-root Package executor → **C-3** restricted Site Worker / adapter |
| **Get Result** | Read Job status, receipt, execution logs and actual hardware evidence | Existing Runtime, journal and receipt; no separate result engine |

B1/B2/B3 and C-1/C-2/C-3 are **internal components**, not six operator actions. No separate B4 button, B4 public API, activation service, second Job engine, second FPGA loader or broker framework is required.

## Stage B: exact current boundary versus intended behavior

- **B1** transfers and commits Bundle bytes; **B2** performs data-only admission. Neither grants installation, execution or FPGA configuration.
- **B3 with `fpga_load: false`** performs verified install/staging **only**. It does **not** publish `assets/active.json`, load FPGA, restart Runtime or touch DUT. `B3_INSTALL_QUEUED` is not `ACTIVE` or `READY`.
- **B3 with explicit `fpga_load: true`**, for a qualifying Bundle containing an FPGA Image, uses the existing Coordinator and protected Root transaction, with fresh operation authorization, Runtime quiescence and Root Image Identity validation. On verified success it can publish the selected Active Set; on failure or unknown outcomes it must fail closed and retain the required journal/recovery semantics. This is **one authorized B3 transaction**, not a fourth user-visible deployment stage.
- Only one verified **Active Asset Set** can be selected per PPU. Multiple immutable Sets may be staged. Preserve exact Bundle ZIP SHA256 identity, atomic pointer replacement, per-Job Set pinning, no mid-Job switch, rollback/recovery evidence, Root Guard and single hardware ownership.
- **Design/implementation gap:** how to select a *non-FPGA* or install-only staged Set as Active without a standalone B4 operation must be reviewed and implemented before claiming the three-operation workflow is complete for all Bundle types. Do not silently change `fpga_load:false` to auto-activate, and do not claim the current implementation already does so.
- B3 FPGA loading and a future programming-flow FPGA Hardware Manager check are separate control decisions. The programming-flow check/load in [ADR-0004](../adr/0004-fpga-image-lifecycle-and-job-driven-loading.md) is not yet a qualified implementation. Loading is never an implicit consequence of upload or Package presence.

**Retired terminology:** Older design/evidence documents, code names or receipt fields may still say `B4`, `b4_activate` or `activate_staged_asset_set`. Keep them only for historical evidence or *internal* atomic Set-selection/recovery mechanisms. They do not define an additional operator step or authorize deletion of safety logic.

## Stage C: exact current boundary

- **C-1**: authoritative PPU-exclusive Package Action lease, Site resource declaration, Runtime quiescence and authorization.
- **C-2**: controlled Python/native-C Package lifecycle, UID isolation design, timeout/cancel, journal and receipt.
- **C-3**: local Worker with a restricted Hardware Adapter. The present ABI-v5 adapter is **Site 1/2 `probe` only**, not Package-driven Flash Erase/Program/Verify.
- Stage C production-integration code is merged, but the formal `plasma-server` **Runtime trigger/caller still needs wiring**. Z2's installed Runtime and actual UID/systemd/Root/OpenOCD integration need independent qualification.
- Eight-Site parallel programming and per-Site concurrent Job leases are **not qualified** merely because Site IDs 1..8 exist in manifests.

## Get Result and acceptance

A reported result must bind Job ID, Site ID, target IC, chosen Set and Package identities, operation, completion state and appropriate receipt/error evidence. `AUTHORIZED_NOT_EXECUTED`, Host-only PASS, a successful install, `ACTIVE` and `READY` are **not** proof of target Flash E/P/V/R.

The public workflow remains **Install → Run → Result**; failure handling, distinct privileges, explicit FPGA configuration authority, Root Guard, Site Admission, SAFE_OFF, Golden recovery and hardware uncertainty handling remain internal, enforced boundaries.

## Migration / documentation policy

- New/current user-facing documents **must not** instruct an operator to execute B4 separately.
- Update active diagrams/terminology to B1–B3 and C-1–C-3. Mark earlier B4 proposals **historical/superseded for operator flow** rather than rewriting retained evidence, historical tests or deployed receipt schemas.
- Do **not** change API fields, scripts, bootstrap behavior, asset-set activation code, hardware operations or security guards in a documentation-only PR. Any outstanding mismatch is a separately approved implementation gap.
