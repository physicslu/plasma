# NXP ADR-0002 Phase 1 v16 — K32L2Ax four exact official Datasheet rows

This update modifies only IC Information manufacturer metadata in
Draft PR #847. Programming and PLASMA Compatibility remain deferred.

## Original NXP manufacturer evidence

Official NXP `K32L2Ax` PDF Rev 3 **02/2021**:
https://www.nxp.com/docs/en/data-sheet/K32L2Ax.pdf

- **Printed page 5, Table 1:** four exact commercially admitted
  `K32L2A31VLH1A`, `K32L2A31VLL1A`,
  `K32L2A41VLH1A`, `K32L2A41VLL1A`.
  The first two contain **256 KB Flash / 128 KB SRAM**,
  the last two **512 KB Flash / 128 KB SRAM**.
- **Printed page 36, Table 12:** operating
  `VDD = 1.71–3.6 V` and separately
  `VDDA = 1.71–3.6 V`, plus
  `VDD–VDDA = −0.1–+0.1 V`.
  Absolute maximum voltages from Ratings (Table 11) must not be
  substituted for recommended operating requirements.
- No documented separately powered `VDDIO` was proven from these
  sources; **I/O Supply remains UNKNOWN**.

All four original **ADMITTED** internal manufacturer exact identities
retain their prior identity status and original Flash field.
Only the missing RAM/VDD/VDDA Phase 1 fields gain VERIFIED values
against the exact official ordering table and series operating
requirements. PDF original bytes have not been permanently archived,
and no verified original PDF SHA256 is claimed.

## Source-blocked K32L2B3x cohort (12)

The NXP official [K32 L2 product page](https://www.nxp.com/products/K32-L2)
lists official `K32L2B3x` Rev 3 and all 12 commercial order numbers,
but official `https://www.nxp.com/docs/en/data-sheet/K32L2B3x.pdf`
was **not retrievable from the research environment**. It would be
incorrect to use the K32L2Ax 128 KB SRAM values for K32L2B.
Existing 12 original `RAM`, `VDD`, `VDDA` UNKNOWN states are
preserved with explicit source-access blockers. No EOL or permanent
incompatibility is asserted.

## Audit

`nxp-501-phase1-k32l2a-enriched-v16.csv`: 501 exact previous source
observations with 4 official-datasheet changes and 12 source-access
blocker notes. All existing v13/v14/v15 results retained, including
LPC84x HVQFN33 32 perimeter contacts + one center VSS pad.

`nxp-phase1-k32l2a-datasheet-lock-v16.json`: exact official
document/revision/page, source v15 Git blob and fields.

`nxp_phase1_k32l2a_v16.py` and tests fail closed on source drift,
unjustified K32L2B field promotions, non-reproducibility, and accidental
Research identity/Phase2/3 changes.

No Production Manifest, IC Selector, Runtime, HIL, socket or site
changes. This is manufacturer data research, not a Programming
Profile or support claim.
