# NXP ADR-0002 Phase 1 v24 — KL25 + K32L2A GPIO I/O evidence

**Scope:** IC Information only. Retains the same **501** source identities (224 admitted / 277 Research-only) and builds on the merged v23 research ledger. No changes to the Production Manifest, Console selector/API/UI, OpenOCD, SWD, PPU, Socket, Site, programming, or HIL.

## Evidence review: 16 exact ordering codes

| Datasheet | Manufacturer version | Exact accepted order codes | Exact SKU ordering table | Normal operating and GPIO reference evidence |
|---|---|---:|---|---|
| [KL25P80M48SF0](https://www.nxp.com.cn/docs/en/data-sheet/KL25P80M48SF0.pdf) | Rev 5 08/2014 | 12 | Ordering Information, physical PDF p2 | Table 4 p6 is **voltage ratings**, NOT normal operating voltage; Table 5 p7 establishes VDD 1.71–3.6 V, GPIO VIH/VIL relative to VDD, and open-drain pull-up to VDD. |
| [K32L2Ax](https://www.nxp.com/docs/en/data-sheet/K32L2Ax.pdf) | Rev 3 02/2021 | 4 | Table 1 p5 | Table 11 p35 is **voltage ratings**, NOT normal operating voltage; Table 12 pp36–37 establishes VDD 1.71–3.6 V, GPIO VIH/VIL relative to VDD, and open-drain pull-up to VDD. |

All 16 have **exact manufacturer ordering-table identity evidence** and already had VERIFIED VDD and VDDA from prior NXP research. The v24 source CSV confirms full exact ICPN, original Flash capacity, manufacturer file/revision and table locator; the generator rejects flash mismatch and any part outside the already-admitted set.

**Crucial trust boundary:** These two original Datasheets directly describe VDD-related GPIO input and open-drain behavior, but do **not** separately establish a programmable independent **VDDIO** power domain. Therefore **16 I/O Supply fields become PARTIAL, not VERIFIED**. The primary I/O Supply field explicitly states the independent VDDIO supply is **NOT established**. Do not claim a per-pin nominal I/O drive-voltage profile, electrically isolated I/O supply, safe socket supply switch, automatic I/O voltage selection, or verified SWD electrical tolerance. The **VIO -0.3 to VDD+0.3 V** row is a pin *rating* and MUST NOT be presented as the normal operating VDDIO range. Similarly, the USB VREGIN maximum must not become a generic I/O supply.

## 224 existing admitted exact NXP ICPN coverage

| Phase 1 field | v23 VERIFIED / PARTIAL / UNKNOWN | v24 VERIFIED / PARTIAL / UNKNOWN |
|---|---|---|
| RAM | 199 / 25 / 0 | **199 / 25 / 0** |
| Working VDD | 135 / 27 / 62 | **135 / 27 / 62** |
| VDDA | 135 / 0 / 89 | **135 / 0 / 89** |
| GPIO I/O Supply | 119 / 0 / 105 | **119 / 16 / 89** |

No Research-only ICPN gets promoted to admitted, and no unchanged field gets silently promoted. Generator asserts deterministic 501-row replay, source Git blob locks, flash and document equality, 16 source rows, no added identities, preservation of all original metadata and field states. Regression tests include malicious source substitutions (fake exact SKU, duplicate, incorrect flash, wrong source revision/page, fabricated source PDF hash, premature VERIFIED and independent VDDIO claim).

**Source integrity limitation:** Both official source PDFs were read and their table/page/revision observations recorded; their original binary PDF bytes were **not archived nor SHA256-qualified**. Git blob SHA locks apply exclusively to our transcription and derived CSV, NOT to original vendor PDF bytes.

## Reproduce

```bash
python data/device-catalog/research/nxp_phase1_kl25_k32l2a_io_v24.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase1_kl25_k32l2a_io_v24.py' -v
```

Still out of scope: software SUPPORTED, Erase / Program / Read / Verify, power sequencing, fixture voltage controls, PL/PS, PPU, HIL, and UI. The remaining **89 UNKNOWN I/O Supply** values require separate official electrical-document review; of particular interest are 12 K32L2B and the remaining MCX C/E/N/W cohorts.
