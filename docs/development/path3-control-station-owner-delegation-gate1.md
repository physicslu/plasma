# Path 3 → Control Station 精準委派 Gate 1（2026-11-15）

## Owner authorization
Owner approved the least-privilege **option B**: preserve SWPC Runner `plasma-codex` UID 998 and Control Station `gordon` UID 1000. Build a **small, reviewed, fixed-path, owner-installed delegation** so a SHA/Work-Order-bound Path 3 request can perform only controlled local Control Station deployment/verification needed for PLASMA PR #1428 and subsequent Resource Set v2 Site 1 HIL. This is not approval to grant a full interactive `gordon` shell, broadly run Codex or Python as `gordon`, copy personal profiles/credentials, replace enrollment, or change Root Guards.

## Security boundaries
- Standalone Draft PR, do not mix privilege installer into PMode/EMode PR #1428; Gate 2 review before merging.
- Existing `scripts/plasmactl-local-control-station` is canonical. Reuse rather than reinvent Manager/BFF deployment. It uses `systemctl --user`; do not silently change UID or user service state.
- Build a trusted **root-owned** immutable command bridge at a fixed absolute path and a **fixed-argv sudoers specification for only that bridge under the operator UID**. It must never dispatch a shell, arbitrary command, arbitrary user-chosen path, or arbitrary environment. Validate caller, arguments, work-order/source identity, clean candidate SHA, service ownership, user runtime, source and rollback plan. Prefer a read-only verification mode and dry-run admission; exact deployment requires an owner-approved, SHA-bound operation and pre/post receipts.
- Sudoers installation or system policy change may happen **only through the existing interactive trusted SWPC administrator channel** after review; **not via the Path 3 Runner**, which has no Linux grant. Preserve credentials and `/run/user/1000` privacy, implement filesystem ownership/permission and symlink checks, and include a reversible, fail-closed installer.
- Avoid granting the runner unrestricted `sudo -u gordon`, `systemctl --user` with arbitrary unit names, `bash`, `python`, `git`, or `codex`.
- Only after the bridge is truly installed and tested may a separately pinned Path 3 HIL task use it for a synchronized Control Station + Z2 Resource Set v2 update. Do not bypass v1→v2 validation, same-boot Root Guard, Job Binding, SAFE_OFF, unknown transaction holds, device ownership, electrical preflight, or Z2 PS-local OpenOCD.
- Functional acceptance: isolated unit/integration/negative tests for forged request/source, environment/argument/path injection, symlinks/permissions, replay, missing user session, privilege confusion; docs with exact trusted admin install/rollback and evidence. Report PASS/FAIL/NOT_RUN, no merge, no sudoers or DUT changes without an effective channel.

## Scope separation
`PR #1428` retains PMode/EMode behavior and host-only fix. This PR handles UID-boundary delegation only. Z2 Provider capabilities v1 `ROUTE_CAPABILITIES_INVALID` remains a separate deployment/version mismatch, and Site 1 HIL is not PASS until a real observed Flash/Verify and matching evidence.
