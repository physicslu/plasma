# ST Coverage Gap v0.5 — Bounded Official Active Commercial Rows

**Observation date:** 2026-09-29. **Research only; Production ST unchanged at 2,683 exact ICPNs / 23 source families.**

## Material progress: minimum gap 5 → 20

The previous five v0.2 sentinels are preserved. This v0.5 source transcribes **20 distinct exact commercial part numbers** with **same-row Active** status from five publicly accessible official ST commercial surfaces, one specifically selected base-product cohort in each entirely absent Production series. Do **not** mistake these bounded samples for all variants in those base products, entire missing families, or the full STM32 catalog.

| Absent Production series | Confirmed same-row Active exact MPNs in this bounded sample | ST official row source |
| --- | ---: | --- |
| STM32C5 | 1 | [STM32C53x–542 official eStore listing](https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus/stm32c5-series/stm32c53x-542.html) |
| STM32H5 | 6 | [STM32H503CB Quality & Reliability](https://www.st.com/en/microcontrollers-microprocessors/stm32h503cb.html) |
| STM32N6 | 3 | [STM32N657A0 Quality & Reliability](https://www.st.com/en/microcontrollers-microprocessors/stm32n657a0.html) |
| STM32WB0 | 2 | [STM32WB05KZ Quality & Reliability](https://www.st.com/en/microcontrollers-microprocessors/stm32wb05kz.html) |
| STM32WL3 | 8 | [STM32WL33CC Quality & Reliability](https://www.st.com/en/microcontrollers-microprocessors/stm32wl33cc.html) |
| **Bounded minimum** | **20** | Five manufacturer surfaces |

The exact identities and evidence-surface URLs are retained in `st-bounded-active-commercial-gap-v0.5.csv`. The verified five-family absence from frozen Production comes from v0.2; v0.4 separately verifies that C5 is MX2-only while its JSON patterns are not exact ordering codes.

## Evidence boundaries

- Official ST `Quality and Reliability` exact-MPN/marketing-status rows are used for H5/N6/WB0/WL3. C5 uses the official eStore item directly labeled Active because the C5 product page's Quality & Reliability column does **not** expose the per-row marketing status in the same manner. All 20 are independent actual listed MPNs; no XML/JSON device pattern was expanded.
- `st-bounded-active-commercial-gap-v0.5.csv` is a **manually transcribed research record**, not a raw, downloaded, SHA-256-bound manufacturer page snapshot. Its Git content is versioned, and the validator checks its schema, exact frozen cohort, source domains/URLs, status, uniqueness, former five sentinels and all 23 frozen Production source hashes; it does **not** claim to re-fetch the manufacturer or reverify lifecycle in CI.
- The official web index can have asynchronous crawl/update dates. The recorded observation date is the audit date, not a vendor-issued as-of snapshot. ST may subsequently alter its commercial status. A complete current Active count remains **UNKNOWN**.
- `20` is a **proven research sample lower bound** within the five missing families; it does not include any unmeasured missing same-family or in-family Production variation. `2683 / 4500` is **not** an Actual Coverage %.
- No Production admission, runtime route, programming algorithm, security, PS/PL, HIL, or physical-validation claim. N6's external-flash/provisioning case must remain separate.

## Reproduce

```bash
python data/device-catalog/research/validate_st_bounded_commercial_gap.py
python -m unittest discover -s data/device-catalog/research -p test_validate_st_bounded_commercial_gap.py -v
```

## Next evidence gate

Obtain a manufacturer-authoritative, complete dated exact-ordering-code + **same-row marketing status** enumeration for scoped STM32 MCU and wireless MCU families, including independent MX2-only C5 and all MX1-covered families. Retain raw vendor bytes, acquisition timestamp, SHA-256, pagination/filter metadata and completeness review. Then compute observed official Active - frozen Production, while retaining unknown/NRND/obsolete separately. Do not publish any of these twenty without the independent identity/metadata/route/admission gate and explicit approval.
