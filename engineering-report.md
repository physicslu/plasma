# Read-only Z2 audit retry — Path 3

- Candidate checked: `c5d1ea789862f43f7e1ef37712c7f7b39493e4de`.
- Trusted-main transport: `c4eafec736054447dca906067e4035ae17d8fb17` (merged PR #1165); candidate transport was not imported.
- Owner Work Order SHA256 independently matched: `fea87dea680be8f19632f189b52b2fcec224d6198a7e2ba040a1844c20abb984`.
- Executor: existing `SWPC-plasma-codex`, Path 3, Run **40195257048**, attempt 1, `development-codex` Job **121174643387**. This report does not assert the still-running workflow's final conclusion.
- Prior identity evidence: Run **40192364384**, Job **121165933881**, artifact **12598359214**; downloaded ZIP SHA256 matched GitHub's `d4c43d2419790df43fcc4ddbec6aba517cbe99955d4ba278f242765e519110b4`. Retry follows Run **40195018566**.

| Acceptance | Observed result |
| --- | --- |
| Installed read-only preflight | PASS; remote exit 0, all six reference file digests matched; root ownership, exact file modes, protected ancestors, source closure and 35 manifest-listed file hashes checked; no symlinks or bytecode found |
| Project profile | PASS; exact project, generic module and pinned candidate SHA matched; legacy F1-B profile digest unchanged |
| Trusted protected audit | PASS; exactly one `execute('audit', candidate_sha, 'pl/projects/z2-bluepill-rbb')`, successful remote exit and validated sanitized receipt |
| Boot identity | `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`, same in preflight and audit |
| FPGA Manager writes/load, MMIO, driver unbind, SWD, Flash, Restore | NOT_RUN; prohibited by this Work Order |
| File installation, service/device changes | NOT_RUN; read-only Z2 inspection only |

Sanitized receipt returned by the unmodified trusted-main transport:

```json
{
  "stage": "audit",
  "source_sha": "c5d1ea789862f43f7e1ef37712c7f7b39493e4de",
  "project": "pl/projects/z2-bluepill-rbb",
  "real_z2": true,
  "boot_id": "4cefdc0c-f586-4d19-b126-1d8e1108c8f1",
  "result": "READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION"
}
```

The transport accepted the receipt only after successful SSH exit and validation of the root result and `hardware_write_authorized: false`. Its returned sanitized receipt omits that field. No direct Root Entry call or alternative stage was used. Enrolled SSH/sudo credentials remained in memory and are excluded from evidence.

Audit blocker: **none**. This result is **READ_ONLY_AUDIT_NOT_HARDWARE_ADMISSION**, never physical admission. Active image identity, electrical conditions, AXI/UIO isolation and safe FPGA recovery were not established by this audit; physical stages remain outside scope.

Evidence: `installed-preflight.json`, `trusted-audit.json` and the bounded inspection procedure in `.plasma-path3-evidence/`. Local procedure exited 0; no source implementation changed and no new test/CI acceptance claimed. GitHub live metadata confirmed PR #1142 open, Draft and at the pinned SHA before execution. No merge or PR-state change performed; keep Draft. No Gate 2 requested.
