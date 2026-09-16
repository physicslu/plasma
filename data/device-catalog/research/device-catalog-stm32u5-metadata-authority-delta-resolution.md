# STM32U5 metadata authority delta resolution

## Purpose

Close the single metadata-authority delta left by the merged STM32U5 metadata policy without inventing semantics or expanding the retained commercial identity set.

The retained target is `STM32U5G9ZJJ3Q`. ST Quality & Reliability lists this exact part as **Preview**, with UFBGA144 package, Internal SMPS, and Industrial grade. The current STM32U5Gxxx Ordering Information authority, **DS14102 Rev 5 (May 2026)**, defines temperature code `6` but does not define temperature code `3`.

## Resolution

This gate resolves the governance question, not the missing manufacturer semantic:

- retain `STM32U5G9ZJJ3Q` as a manufacturer-observed exact identity;
- retain its Preview lifecycle observation;
- accept direct Q&R package / SMPS / grade observations as evidence;
- do **not** infer the missing temperature-code `3` meaning;
- keep the exact part outside the metadata-ready set;
- keep it in manual review / quarantine until ST publishes an explicit U5G authority for code `3` or an exact operating-temperature semantic for the part.

The fact that other STM32U5 Ordering Information documents use code `3` for `-40..125 C` is context only. Cross-document pattern transfer is not exact-product authority.

## Closed scope

- retained Base Devices: 74
- retained exact ICPNs: 266
- metadata-ready Active exact ICPNs: 265
- manual review / quarantined exact ICPNs: 1
- rejected retained identities: 0
- scope expansion: 0
- Production exact ICPNs: 2,017, unchanged

The quarantine target is exactly:

```text
STM32U5G9ZJJ3Q
```

## Manufacturer authorities

1. ST STM32U5G9ZJ product page / Quality & Reliability surface
   - exact part exists;
   - status: Preview;
   - package: UFBGA 144 10x10x0.6 P 0.8 mm;
   - SMPS: Internal;
   - grade: Industrial.

2. ST DS14102 Rev 5, section 7 Ordering information
   - `Z` = 144 pins/balls;
   - flash code `J` = 4 Mbytes;
   - package code `J` = UFBGA 10 x 10 mm;
   - temperature code `6` = Industrial -40 to 85 C (105 C junction);
   - no temperature code `3` definition is present;
   - `Q` = dedicated SMPS step-down pinout.

3. ST product-family description
   - family context states -40 to +85 C (+105 C junction), but this is not an exact ordering-code mapping for code `3`.

## Governance

This transaction remains `research_only` and does not authorize:

- Production admission;
- Preview promotion;
- cross-document temperature inference;
- option-byte or security semantics;
- OEM-key behavior;
- Flash geometry or programming-algorithm equivalence;
- runtime programming or debug attach;
- physical validation or HIL.

## Next gate

The next research transaction is:

```text
stm32u5-canonical-admission-plan-under-security-fence
```

That gate may plan only the **265 metadata-ready Active exact ICPNs**. The quarantined Preview identity remains outside admission scope unless a later manufacturer authority explicitly closes its temperature semantic.
