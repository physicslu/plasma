# NXP manufacturer-only v6: 212 admitted Device evidence and 277 exact gaps

Scope: **ONLY** ICPN Discovery, Manufacturer Device Metadata, Production Catalog.
This does not create a Programming Profile, executable OpenOCD driver, PPU
job admission, socket/electrical/HIL proof, or a deployment.

## What is already admitted

After merged #841 the authoritative Production Catalog remains:
- **4,853** exact ICPNs, **31** canonical sources
- STMicroelectronics **4,629**
- NXP **224** = 12 KL25 + **196 MCX** + **16 K32L2**
- The MCX/K32L2 exact identities are `no_mapping`; no target config.

212 MCX/K32L2 already carry exact-NXP-`/part/` source HTML
metadata in the SHA-locked
`nxp-212-manufacturer-device-evidence-v5.csv`.
Previously that evidence was not visible through Control Station.

## What v6 changes

`software/python/plasma_web/nxp_manufacturer_device_evidence.py`
is a read-only exact-SKU data resolver, not a new Catalog source:
- Verifies the **original** CSV git-blob SHA
  `541a62a9e6bf5a8c79436bd0e09ab1845394b964`.
- Only 212 exact manufacturer and Catalog matches can resolve.
  Package, pin count, Flash, ambient temperature, manufacturer source URL
  and singleton Base Device must agree with the authoritative Production
  Catalog. Drift **fails closed** rather than selecting a different SKU.
- RAM is manufacturer-sourced **212/212**;
  operating VDD is manufacturer-sourced **208/212**;
  other four have explicit null, never a fabricated 0.
- **I/O Supply and VDDA = null for all 212**, not inferred equal to VDD.
- Cross-ordering `Base Device` grouping is **not** independently verified;
  exact SKU singleton is an explicit fallback, not semantic equivalence.
- Returns a separate `nxp_manufacturer_device_profile` response field;
  the existing ST `manufacturer_device_basic_profile` is unchanged.
- Control Station shows RAM, VDD, ambient and **unknown** I/O Supply,
  VDDA, plus exact manufacturer HTML SHA256 and official source URL.
- Every new payload advertises
  `manufacturer_device_full_profile_complete=false`,
  `programming_profile_authority=false`,
  `hardware_runtime_ready=false`,
  `physical_programming_qualified=false`.

**IC Support M1** is not silently upgraded by this partial Manufacturer
Device display profile. Publication of electrical evidence is not
equivalent to complete electrical specification nor to real programming.

## Exact 277 remaining gap review

The already observed NXP Active Exact population is bounded to
**501** from 28 selected official Package/Quality pages; the
global-vendor denominator remains UNKNOWN.

An exact 277-row permanent review queue is introduced:
- **129** original 353-source exceptions:
  85 exact `/part` non200; 8 wireless Flash multi-value; 8 missing
  wireless ambient; 23 i.MX RT Flash/ambient and 5 MCX Flash/ambient.
- **148** newer LPC/i.MX RT Active identities:
  3 LPC5502/04/06 **four basic fields observed but RAM absent**;
  31 i.MX RT1170 partial (package/pin/RAM/VDD source observations but
  internal Flash/ambient unsupported); 114 exact `/part` pages blocked.
- None of these 277 are a Production Catalog exact identity.
- The 3 LPC four-field candidates remain research-only; do not silently
  admit the 145 other newer SKUs and do not assume i.MX RT internal Flash
  = 0 from externally booted architecture.

Queue source inputs are pinned with Git Blob SHA:
`nxp-353-metadata-gap-review-queue-v3.csv`,
`nxp-148-new-official-metadata-review-v5.csv`,
`nxp-212-manufacturer-device-evidence-v5.csv`, and the current
Production Manifest. This gives 277 exact negative decisions, not a
misleading "vendor-wide coverage percentage".

## Owner gate and verification

This PR is a **single large Manufacturer Device/API + bounded Discovery
review transaction**. It changes no Production Manifest count, no
Programming Profile or actual programming backend. All exact source
bindings, Control Station pagination and untouched ST UI should pass
repository and v6 dedicated Python/TypeScript CI.

Merge requires ONE explicit owner approval after final CI verification.
Runtime Control Station deployment is a separate operation; merge does
not imply release/service restart or hardware validation.
