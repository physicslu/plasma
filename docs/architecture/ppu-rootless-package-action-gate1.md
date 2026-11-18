# PPU Appliance: Package Action Runtime and Non-root FPGA Privilege Model — Gate 1

Status: **Gate 1 design / feasibility only**. Implementation, Z2 permission audit, HIL, deployment and Gate 2 merge are NOT_RUN. Created as an independent PR from main (base 6ec8350f7a873aa62c3eda3140c2a40df2824644).

## Owner direction and scope split

The PPU is a standalone, owner-operated physical IC programmer; do not impose a multi-tenant cloud privilege design without a demonstrated threat boundary. FPGA loading and execution of a Python Package belong to one **typed Package Action** lifecycle. Normal operations should not require the operator to use sudo or SSH.

This PR is **not PR #1261**. Keep #1261 focused on delivering Bundle v3 and HTTP B1/B2/B3 with explicit fpga_load=true, correct Runtime Quiesce, FPGA Manager load, Image Identity, receipt, journal and current recovery semantics. Do not delay #1261 or its known-good ab79b04e HTTP HIL waiting for the privilege redesign. New FPGA ABI-v5 Image and Site2 DPIDR are subsequent, separate HIL evidence.

Related independent Draft PR #1252 already introduces a **typed, host-only Asset Execution Layer** for Python, Native C and FPGA. Reuse and converge on its single dispatch and action identity instead of inventing a second execution engine, parallel endpoint or duplicate Executor registry. #1252 is not executable/hardware-qualified.

## Desired architecture

Common control plane:
- Bundle v3: B1 Receive → B2 exact-package/Bundle Admission → B3 Install/Verify.
- Explicit typed action request: package identity, exact immutable Asset Set SHA256, action kind and arguments allowed for that kind; the controller never supplies an executable shell command or arbitrary filesystem path.
- Coordinator: validates current device/source, obtains Job and FPGA-specific locks when necessary, dispatches the trusted handler, writes journal and receipt, and reconciles unknown outcomes.
- Python Package handler: run in a bounded **non-root** process with only its declared data and minimal permitted resources. Installation alone never executes Python. Python must not gain FPGA programming privileges merely by residing in the same Bundle.
- FPGA Image handler: install and load through Linux FPGA Manager with exact BIN/HWH/Manifest and image identity, Golden recovery and exclusive owner fence. **Aim for non-root execution where Z2 kernel permissions can prove it is feasible**, otherwise use the smallest fixed-purpose privileged action. The high-level HTTP API remains the owner-facing entry point and must not require SSH for normal operation.

Same lifecycle and receipts does NOT imply same Linux UID, Linux capabilities, mount namespace or hardware access.

## Existing implementation facts to preserve

- scripts/ppu-bootstrap.py currently runs Bootstrap as root with ProtectHome=true and PrivateTmp=true.
- scripts/ppu-bootstrap-deployment.py in #1261 uses systemd-run to invoke a protected Root Entry outside the Bootstrap mount namespace. It is part of the existing deploy implementation, not an authorization to build a new generic Root launcher.
- scripts/z2/plasma-path2-root-entry currently sources code from /root/plasma-path2-approved and enforces UID 0; direct compatibility migration belongs to a separately reviewed change, not an implicit #1261 refactor.
- pl/hil/fpga_image_guard.py:read_live_z2_facts and RootZ2TargetPort.exclusive require effective UID 0; FPGA image write uses /sys/class/fpga_manager/fpga0/firmware, real readback uses dmesg /proc and MMIO. The current implementation is **not** rootless.
- The Linux FPGA Manager firmware sysfs permission, /lib/firmware install/write, FPGA readback and MMIO access constraints must be measured on the actual Z2. Root is NOT a theoretical FPGA hardware requirement, but non-root support is not established by Host-only tests.
- Existing controls remain: runtime hold_asset_activation lease, FPGA reload owner lock, exact firmware SHA256/ABI and device identity, programmed image/Golden recovery, fail-closed journals, and no unrequested DUT operation. TIMING-18 remains OPEN/NON_BLOCKING for engineering testing, not external-clock qualification.

## Proposed implementation plan (not yet authorized as completed)

1. On Z2, collect a read-only permission matrix: running service UIDs, relevant systemd service sandbox, stat/ACL/owner/mode of /sys/class/fpga_manager/fpga0/firmware and state, /lib/firmware, /dev/uio* /dev/mem, the private runtime-control socket, /proc and kernel-log access; verify effective capabilities and the actual kernel/driver. Record PASS/DENIED/NOT_RUN rather than assuming rootless works.
2. Define exactly one trusted execution API and one cross-kind Package Action receipt/journal schema. Reuse #1252's typed executor seam where applicable; do not silently replace #1261's current HTTP B3 and receipt schemas or change its approved live HIL.
3. Prefer a dedicated unprivileged Service identity for ordinary action planning and Python execution. Non-root FPGA load can be used only after real proof of all required kernel/file rights and adequate confinement of untrusted Python. If needed, narrowly scope a dedicated privileged FPGA handler; do not grant blanket FPGA sysfs or root-owned firmware write access to arbitrary Package Python.
4. Move normal operational source/state out of /root only when tested as an atomic, evidence-backed migration. Proposed locations: immutable application under /opt/plasma, state/journal under /var/lib/plasma, device firmware under the kernel-supported firmware directory. Keep legacy protected root recovery path until replacement is proven and do not remove any recovery capability by assumption.
5. Avoid new generic systemd-run Root command service or blanket sandbox disablement. If a privileged bridge remains necessary, fix its allowlist and authorization model to the single FPGA operation rather than user-supplied shell or binary paths; document the security/runtime impact precisely.
6. Add Host-only integration tests covering shared action identity and receipt, non-root Python execution, denied FPGA sysfs attempts from Python, wrong identity/SHA/ABI, busy Site Job, missing quiesce, mid-flight failure/timeout, unknown write outcome → recovery_required, kernel permission denial and working recovery. Follow with real Z2 permission and hardware evidence under a separately explicit HIL scope.

## Acceptance and delivery gates

Gate 1 implementation readiness requires: a Z2-backed privilege feasibility report; explicit owner decision about any irreducible privileged FPGA access; a minimal, non-overlapping change list for #1252 / #1261 / this PR; and test/CI and migration plan. If a genuinely rootless FPGA write is blocked by current kernel permissions, report that accurately instead of weakening Linux permissions without review.

Gate 2 requires a specific merge-ready PR with exact HEAD, CI, reviews, threads, rulesets and mergeability. This planning PR must remain Draft until further implementation and owner Gate 2 approval.

Not included here: changing or merging #1261; loading FPGA; testing Blue Pill DPIDR; modifying Bootstrap/Z2; executing a Bundle Python on the device; granting extra permissions to Bootstrap.

## Consolidation tracking

This design is carried by Draft PR #1252 (superseding Draft PR #1262 without merging #1262). Host-only CI does not validate actual Z2 uid/gid/ACL, firmware loader access, `/dev/mem`, UIO, `/proc`/dmesg, current boot or hardware recovery. Each remains **NOT_RUN** pending a separately authorized Z2 permission assessment. PR #1261 remains untouched and its `fpga_load=true` path is the sole existing owner of the explicit B3 FPGA load transaction.


## Current implementation cross-check (after #1261 merged)

PR #1261 has subsequently **merged into main** with the existing B3 v2
FPGA-load receipt and protected Root Loader. PR #1252 reuses that contract
through a host-only, read-only receipt-binding validator; no second FPGA
Writer or privileged bridge is introduced. The #1262 plan remains carried
in #1252. A fully unprivileged Z2 FPGA Manager write, safe Root Guard
replacement and real non-root Python/Native execution have **NOT_RUN**
evidence; do not infer capability from the new Host-only tests.
