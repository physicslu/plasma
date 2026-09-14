# STM32L1 Phase L1.3 — Manufacturer-Authoritative Metadata Policy

## Status

Gate 1 scope is complete as a research-only metadata policy over the immutable L1.2 commercial set.

- Family: `STM32L1`
- Frozen input: **59 Base Devices / 144 Active exact ICPNs**
- Excluded non-Active exact variants: **62**
- Metadata-ready: **144**
- Manual review: **0**
- Reject: **0**
- Exact-part metadata exceptions: **0**
- Production writes: **0**
- STM32L1 Production exact ICPNs: **0**
- Existing Production: **1,718 exact ICPNs / 530 Base Devices / 12 families**

L1.3 does **not** authorize canonical admission, Production publication, programming policy, Flash geometry equivalence, option/security programming semantics, physical/HIL qualification, PPU deployment, or runtime programming support.

## Authority model

Commercial identity and lifecycle remain governed by the immutable L1.2 retained official-ST exact-set evidence.

Metadata is decoded only from official ST datasheet **Ordering Information**. The deterministic fields are:

- series / Base Device
- package
- pin count
- Flash-size code
- temperature grade
- option / generation / packing suffix
- source authority / source reference / verification state

The policy is fail-closed. Identity outside the retained L1.2 Active set is rejected. A retained identity that cannot be uniquely decoded by one authority record becomes `manual_review_required`.

## Why ten authority records are required

A subfamily-level shortcut is not safe for STM32L1.

The retained 144-ICPN scope requires ten deterministic Ordering Information records:

| Authority | Official ST document | Retained scope |
| --- | --- | --- |
| `l100-gen-a` | DocID025966 Rev 6 | STM32L100 x6/x8/xB Generation-A |
| `l100-xc` | DocID024995 Rev 5 | STM32L100 xC |
| `l15-gen-a` | DocID024330 Rev 5 | STM32L151/L152 x6/x8/xB Generation-A |
| `l15-xc-low-pin` | DocID022799 Rev 13 | STM32L151/L152 xC, C/U pin codes |
| `l15-xc-high-pin` | DS10262 Rev 8 | STM32L151/L152 xC, R/V/Q/Z pin codes |
| `l15-xd` | DS8576 Rev 13 | STM32L151/L152 xD |
| `l15-xe` | DS10002 Rev 10 | STM32L151/L152 xE |
| `l162-xc` | DS10287 Rev 6 | STM32L162 xC |
| `l162-xd` | DS8669 Rev 11 | STM32L162 xD |
| `l162-xe` | DocID025882 Rev 7 | STM32L162 xE |

The `xC` low/high split is intentional: the retained low-pin C/U devices and high-pin R/V/Q/Z devices are governed by different official Ordering Information tables. Collapsing them would create a false family grammar.

TN1176 remains the migration authority for non-A versus Generation-A identities. `A` is retained literally as manufacturer generation/identification metadata and is never used to collapse one commercial identity into another.

## Exact-part exceptions

The final full replay requires **zero** exact-part exceptions.

`stm32l1-phase-l1.3-exact-variant-exceptions.json` is therefore an immutable empty whitelist. Any future non-empty exception requires separate evidence and review; the current L1.3 validator rejects it.

## Frozen deterministic result

```text
manufacturer-verified Active exact ICPNs: 144
metadata-ready exact ICPNs:              144
manual review:                             0
reject:                                    0
exact metadata exceptions:                 0
```

Hard result hashes:

- metadata-ready exact set: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- metadata rows: `c794a21a63e72d805170034defe4af4e749ce456966f9083efe2f4abfa4fe247`
- empty manual-review set: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- empty reject set: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Distribution checks:

- Flash: 32 KiB 12, 64 KiB 18, 128 KiB 21, 256 KiB 45, 384 KiB 24, 512 KiB 24
- Package: BGA 29, LQFP 91, UFQFPN 13, WLCSP 7, WLCSP64 1, WLCSP104 3
- Temperature: -40..85 C 137, -40..105 C 7
- Suffix: blank 45, A 36, ATR 15, D 10, DTR 3, TR 35
- Series: L100 8, L151 65, L152 48, L162 23

## Hard-lock bindings

- L1.2 discovery baseline SHA-256: `2f44e54dfac6904cc9af485e14eeb54e2d1a564f1cb633668fdf8f3a78ab4f92`
- L1.2 Active exact-set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- L1.3 Ordering authority SHA-256: `c689e848a58a45e3b1d855e56f9a4bba5fb953a89a9565091c687fc7bb392bc9`
- L1.3 exact-exception file SHA-256: `1b2c4bba21169e1351185d094b0da984ed2c0f03b4fb5ddf1edb431b9e74a763`
- L1.3 frozen baseline SHA-256: `6da49ceda71a3611244e1961e6aca3809d5809f8f7106834123c6ae48e726e62`
- Production manifest Git blob: `1aa2311a25a69742c428147a402816ed5071e04e`

Permanent validation rebuilds the baseline byte-for-byte, revalidates L1.2 retained evidence, locks all authority digests, requires the empty exception whitelist, checks 144/0/0 disposition, and enforces zero Production diff.

## Next phase boundary

L1.4 may define a bounded read-only capability/admission plan only after a separate Gate 1 approval. L1.3 itself admits and publishes **zero** STM32L1 ICPNs.
