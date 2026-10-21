# PLASMA Path 2 — Z2 Site 1 F1-B minimal live HIL handoff

**Scope:** one owner-authorized Development HIL using the existing exact F1-B
candidate and `base.bin`; AXI isolation remains **UNPROVEN** under the
owner-approved bound-passive UIO risk. No DUT, LA, power or unrelated
hardware. No Vivado rebuild. No merge or production deployment.

## Confirmed facts — do not repeat old qualification

- Prior **real** complete F1-B load / 3×read-only MMIO Identity /
  restore passed in [Run #39395142726](https://github.com/physicslu/plasma/actions/runs/39395142726).
  It was a one-process Path 3 sequence, **not** the Path 2 multi-trigger test.
- Candidate F1-B `/lib/firmware/plasma-f1b-owner-20261020-once.bin`,
  SHA256 `c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3`.
- Original `/lib/firmware/base.bin`,
  SHA256 `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`.
- Fixed BIT SHA256
  `fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075`.
- The existing SWPC→Z2 path previously authenticated SSH and privileged
  sudo using the **owner's local credential store and pinned host key**.
  Do not place credentials or unredacted command output in GitHub.
- The last SSH-only Z2 baseline [Run #39522633934](https://github.com/physicslu/plasma/actions/runs/39522633934)
  passed partially with Manager `operating`, but did not establish root,
  current image, AXI quiescence or any new FPGA operations.

## Exact implementation to stage for review

Use **only an immutable, clean** authorized PR #1082 commit. Verify its
exact SHA after choosing the reviewed commit, and transfer the reviewed
tree to a **root-owned, non-group/world-writeable** directory on Z2.
Use the previously reviewed SWPC→Z2 credential/host-key transport; do
not add a runner, modify sudoers, place passwords in argv/history, or
execute Python files directly from a mutable PR checkout as root.

The **only** live implementation for this handoff is
`pl/hil/path2_f1b_minimal_stage.py`, with these existing dependencies:
`pl/hil/path2_f1b_dev_risk.py`, `pl/hil/path2_z2_target_guard.py`,
`pl/hil/f1b.py`, `pl/hil/swd04/one_shot.py`,
`pl/hil/swd04/development.py`, `pl/hil/swd04/contract.py` and
`software/python/plasma_interfaces/linux_mmio.py`, plus their package
initializers and imported local support code. The target program itself
checks root identity, protected source, exact ARMv7 native interpreter,
current process/driver ownership, firmware digests and shared FPGA lock.

Do **not** reuse the old `f1b-path3-z2-hil-once` task/one-shot claim.
Do **not** use the disabled Path 2 Dispatcher as a fake live callback.
The existing `z2-path2-download` / `z2-path2-testing` still intentionally
return `PATH2_LIVE_PROVIDER_NOT_REGISTERED`. A separately reviewed
authorized SWPC root execution route remains necessary; this document
does **not** create or grant that privilege.

## Three independent manual stage invocations

After the code has been installed at its reviewed immutable SHA and
the trusted root operator verifies fresh Site1 status, invoke the
following **one stage at a time**, on Z2 using the same protected
root environment and source directory:

```sh
export PLASMA_DEV_RISK_ACK=PLASMA_PATH2_F1B_SITE1_20261021_ONCE_BOUND_PASSIVE_UIO
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage download
# Separate operator trigger after successful Download; no automatic transition:
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage test
# Separate operator trigger after successful read-only Testing:
/opt/plasma/python/3.12.13/bin/python3 -m pl.hil.path2_f1b_minimal_stage restore
```

The string containing `ONCE` identifies the owner's **specific initially
approved physical HIL risk acceptance**; it is not a permanent prohibition
on repeating normal operations in the target implementation. Repeated
Download/Test/Restore within an authorized Development session are
supported, but this handoff does not itself grant additional real HIL
sessions outside the owner's authorization.

**Stop criteria:** unknown firmware/manager state, a changed Boot ID or
candidate/base hash, other active MMIO consumer, unavailable root route,
SIGBUS/stalled or unreaped child, or a failed FPGA Manager write. Do not
blindly retry after uncertainty; preserve the root checkpoint for an
informed physical recovery decision. A verified `base.bin` allows an
idempotent `ALREADY_RESTORED` no-op.

## As-run evidence and acceptance

For each separately invoked stage, capture actual invocation timestamp,
installed Git SHA, remote root UID, boot ID, stage exit code, sanitized
`PLASMA_F1B_PATH2_DEV=` JSON result, target root-owned checkpoint
(`.plasma-f1b-site1-development-state.json`), bounded native child
result and Manager load/restore log evidence.

Accept **one real Path 2 HIL** only if:
- Download observed `LOADED_AND_HELD` on actual Z2.
- An **independent** Testing trigger produced exact three Identity
  words (offsets 0, 4, 0x4000; 3 native 32-bit reads, zero writes).
- An **independent** Restore trigger returned `RESTORED_VERIFIED`
  with original Manager/base state, and no unintended DUT/LA/power work.

Host-only fake-device results are **not** equivalent to these results.
If there is no separately authorized installed root route, final result
remains `REAL_HIL_NOT_RUN` with the concrete missing execution boundary;
do not declare success or invoke an untrusted PR as root.
