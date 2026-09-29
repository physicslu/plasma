# ST C5 Source-only Candidate Gate v1.0 — 33 Exact Metadata Gaps and Local Loader SHA256

**2026-09-29. Research-only.** Follows the merged #680 crosswalk.

## Source baseline and missing Exact Variant triage

The ST [`stm32c5xx-dfp` source](https://github.com/STMicroelectronics/stm32c5xx-dfp/tree/a5f65bc64535cfa723e9d25f58d7ce23d0937aed) still points to commit `a5f65bc64535cfa723e9d25f58d7ce23d0937aed` at its observed latest main on 2026-09-29 (pack v2.1.0; PDSC release date 2026-05-04). Its PDSC is an IDE Device Family Pack — **not a manufacturer-certified exhaustive commercial order-code listing**. The eStore evidence snapshot of 172 same-card Active exact commercial IDs was captured 2026-09-29.

Reconcile all 172 with the locked DFP: **139 exact `Dvariant` matches; 33 official eStore exact commercial identities have a unique DFP Base Device but are not present as exact DFP Variant entries.** The 33 missing exact rows are preserved, separately and without wildcard expansion, in `st-c5-dfp-33-exact-variant-triage-v1.0.csv`.

| Subcohort of the exact-DFP-absent 33 | Count | Interpretation |
| --- | ---: | --- |
| TR-suffix exact commercial MPN with its *non-TR exact counterpart* in pinned DFP | 9 | A reference candidate for further packaging/temperature and electrical applicability review, **not** permission to strip TR for programming, nor proof of equivalence. |
| TR-suffix exact MPN without its stripped exact non-TR DFP counterpart | 11 | Independently needs exact order-code/metadata evidence; never reconstruct from a product-name pattern. |
| Non-TR exact MPN absent from pinned DFP `Dvariant` | 13 | Independently needs exact manufacturer ordering table/selector evidence. |
| **Total** | **33** | All remain `backend_route_ready=false` and `exact_variant_metadata_verified=false`. |

No missing MPN is called NRND, inactive or invalid by its absence from the earlier DFP. A Base Device's flash/loader details are a structural *candidate* only, not an exact retail-part programming authorization.

## Non-executable, explicitly staged candidate preflight

`preflight_st_c5_local_loader_candidate_v10.py` implements a pure, **non-executable** chain, re-validating v0.9's original frozen 172-source and Production SHA contracts before interpreting any input:

```text
Exact research ICPN (no generated SKU)
   -> source-locked DFP exact Dvariant REQUIRED (blocks the 33)
   -> independently supplied canonical DEV_ID string (0x44F/0x44E/0x45A)
   -> source-matching DEV_ID REQUIRED
   -> independently supplied integer FLASH size in bytes
   -> exact DFP flash geometry match REQUIRED
   -> caller explicitly supplies a local staging directory
   -> literal pinned official DFP loader filename + SHA256 / ELF32 little-endian
   -> SOURCE_MATCHED_RESEARCH_ONLY
```

The last state is **not** a runtime admit. Caller-provided DEV_ID and Flash size are untrusted assertions in this tool and are **not** obtained from real hardware. The preflight neither executes OpenOCD nor emits an executable command, and cannot change the catalog. A successful source-only result always reports `hardware_readback_authenticated=false`, `hardware_runtime_ready=false`, `catalog_admission_ready=false`, and `production_write_authorized=false`.

It refuses invalid/unknown exact identities, unqualified 33 Base-only variants, wrong claimed DEV_ID or Flash geometry, absent source, URL paths, symlinks, unexpected ELF bytes or mismatched SHA256. It makes no network requests at runtime and does not download a loader or add one to the repository. Three official DFP loader SHA256 values remain pinned to v0.9's reviewed source ledger. ST OpenOCD's original scalar-vs-array Tcl bug is **not** silently fixed or activated by this research tool.

## Reproduction

```bash
python data/device-catalog/research/preflight_st_c5_local_loader_candidate_v10.py
python -m unittest discover -s data/device-catalog/research -p test_preflight_st_c5_local_loader_candidate_v10.py -v

# This intentionally BLOCKS without real, locally staged, source-verified loader bytes:
python data/device-catalog/research/preflight_st_c5_local_loader_candidate_v10.py \
  --icpn STM32C531CBT6 --reported-dev-id 0x44F \
  --reported-flash-bytes 131072
```

Separate GitHub CI performs fixed-commit source-only replay, temporarily fetching three public DFP loader bytes into an isolated CI directory, independently verifying v0.9 SHA256, and exercising one *non-executable* positive candidate from each of the three loader groups. The bytes are **not uploaded as artifacts, committed to Plasma, executed or used to program hardware**.

## Still blocked before genuine admission

1. Obtain exact commercial-order-code evidence for 33 missing DFP variants (physical package, suffix meaning, flash/RAM, temperature and lifecycle in suitably dated manufacturer rows), with raw provenance.
2. Independently review official DFP binary redistribution terms and any downstream/packaging obligations. Current SHA pin is provenance, not a legal signoff.
3. Correct the ST OpenOCD Tcl scalar/array lookup in an isolated target candidate and prove the *selected* Plasma PS build includes `stldr`, compatible versioned loader, and memory geometry.
4. Validate a read-only real DEV_ID/Flash-size probe and controlled HIL before discussing flash erase/write/verify qualification.
5. Seek owner approval in a separate Production ICPN publication PR; **ST Production stays 2,683 exact / 23 families**. No security-state, option-byte, RDP, OTP or mass-erase operation is authorized here.
