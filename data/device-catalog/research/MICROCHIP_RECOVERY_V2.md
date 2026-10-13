# Microchip Research v2 — 8 timeout recovery, not Production SKU admission

**Starting base:** merged Research PR #829, commit `7c162f66faece70b0ce330ca78390e3c774738c4`.

The DFP name query first pass covered 3,198 planned search names, but
eight whole batch archives were quarantined due to hard timeout before
the original attestation was written. Their exact names are pinned in
`microchip_mcp_timeout_recovery_v2.py`. They are ALL 8-bit PIC/AVR;
no different manufacturer inventories are touched.

The recovery runs **each individual DFP name in an isolated subprocess**,
with a bounded 85-second query watchdog and three-second serial gap.
Only two batch jobs execute concurrently. Each source proof is
durably fsynced BEFORE any Microchip vendor call; any failed query
retains original response diagnostics and stays unverified. The original
eight quarantined raw archives are never rewritten or post-hoc attested.
Offline `microchip_mcp_evidence_ledger_v1.py` must replay raw response
bytes before a candidate can be included in Research counts.

`NOT_FOUND` does **not** imply device EOL. DFP support names are not
commercial SKU enumeration and measured text-search Active labels are
not authoritative manufacturer life-cycle classification.

**Authorization boundary:** this work does not create or alter Production
ICPN catalogs, flash firmware, OpenOCD mappings or global Active coverage
claims. A separate owner approval will be required for PR merge and for
any later Production data promotion.

## Completed original-source recovery audit (2026-10-13)

The real read-only GitHub Actions [recovery run #38373429583](https://github.com/physicslu/plasma/actions/runs/38373429583)
finished **8/8** batches successfully. All **80/80** targeted 8-bit
device-support queries completed exact raw-response replay. Each original
batch source attestation was written and fsynced before its vendor requests.
The previous eight quarantined timeout ZIPs remain unaltered.

An additional byte-level offline reconciliation checked **423** archived
recovery response files against their manifest SHA-256, rederived each
positive ordering identity from Microchip's original 20-row pagination walk,
verified original DFP identity/plan hashes, and checked raw lifecycle
consistency with the first-pass source-linked research ledger. Results:
- **775** new distinct exact-prefix candidate ordering identities.
- **23,276 -> 24,051** unique *Research* candidate identities in total.
- Raw vendor lifecycle observations: **23,801 Active** and
  **250 Not Recommended For New Design**; **0** cross-source conflicts.
- First-pass original **80** incomplete query slots are now all replayed.
  Remaining **297 NOT_FOUND** observations are verified negative searches,
  NOT verified EOL SKU identities.
- The manufacturer global orderable-SKU/Active denominator remains **unknown**.

Each of the eight immutable raw recovery ZIPs is preserved in the existing
[Microchip evidence folder](https://drive.google.com/drive/folders/1sJHR73lEjJeAgLt7pa4nJgpAr4Wrj50f).
Exact ZIP SHA-256 and Research count invariants are frozen in
`microchip-mcp-recovery-v2-observation-20261013.json`; CI rejects
Production promotion and inflated coverage claims. The standalone external
reconciliation SHA-256 is recorded in that snapshot.

**Approval boundary:** this PR can only merge Research acquisition/replay,
source evidence tests and the Research snapshot. It must not import or
publish Production ICPNs, infer that `Active` raw text-search rows are
independently certified current ordering SKUs, or mark any PLASMA flashing
backend supported. Independent manufacturer ordering-code and lifecycle
verification is separate future work.
