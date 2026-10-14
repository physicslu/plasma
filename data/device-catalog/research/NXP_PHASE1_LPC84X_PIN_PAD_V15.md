# NXP IC Information v15 — LPC84x HVQFN33 / HVQFN32 nomenclature reconciliation

**Phase 1 only.** No code changes to Production Identity, software OpenOCD qualification,
public IC Selector, Site/Socket/PPU, Adapter/HIL or actual firmware programming.

## What the original v14 data said

In v14 five `JHI33` exact commercial ordering variants were flagged `CONFLICT`
for `package` and `pin_count` because the NXP LPC84x Rev.2.1 Datasheet
calls the package **HVQFN33**, while the official LPC84x Package/Quality tab
labels the commercial group **HVQFN32**.

## Independent package outline resolves the apparent mismatch

A recheck of the same original official NXP document found **both**
statements to be mechanically interpretable, not evidence of two
different physical packages:

- **Table 1, page 4** identifies package **HVQFN33** / **33 total terminals**,
  NXP outline SOT617-11.
- **Figure 7, page 11** shows precisely perimeter terminals **1–32** and
  central pad **33 VSS**.
- **Figure 42, page 85** describes **32 perimeter terminals** on the
  physical **HVQFN33** outline. The center pad is an exposed ground contact.
- NXP official **Package/Quality** commercial SKU group is called
  **HVQFN32**, referring to the 32 perimeter contacts.

The Phase 1 `Pin Count` column now explicitly means **peripheral/perimeter
physical package contacts**, so these five ICPNs are **32**, not 33.
Other fields retain the source-specific package name `HVQFN33`; its
commercial alias `HVQFN32` is stored separately. In the new columns
`thermal_pad_count=1`, `thermal_pad_contact_number=33`,
`thermal_pad_net=VSS`, and `electrical_contact_count_including_pad=33`.
The 5 pairs of `package_state` / `pin_count_state` become
`VERIFIED` (explained/reconciled), **not** `CONFLICT`.

**Important:** The 32+1 breakdown is manufacturer IC Information.
How to physically ground/bond the thermal pad in a particular Socket,
Adapter footprint, Site or fixture is **Phase 3**, not authorized here.
No silicon revision or OpenOCD Flash operation is inferred.

## Reproducibility and epistemic limitations

`nxp-501-phase1-pin-package-reconciled-v15.csv` is a deterministic
501 exact-SKU derivative of **immutable** v14 CSV. All other 496 exact
rows retain previous values/states; existing 224 admitted identities and
277 Research-only entries remain unchanged. v14's original five
historical CONFLICT observations remain available as audit evidence.

Official URL + revision + page/figure + commercial alias are recorded in
`nxp-phase1-pin-package-evidence-v15.json`. The original NXP PDF bytes
are **not** stored; we make no claim of a verified original PDF SHA256.
CI checks pinned Git blob input and tests 32+1 semantics, all five
exact SKUs and fail-closed Phase boundary.

Sources:
- https://www.nxp.com/docs/en/data-sheet/LPC84x.pdf
- https://www.nxp.com/products/LPC84X?tab=Package_Quality_Tab
