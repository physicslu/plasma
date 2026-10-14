# NXP P0 — 27 exact ordering parts, pinned OpenOCD source Flash/ID/security v11

> **Archived for ADR-0002 Phase 2 Programming (owner scope change, 2026-10-14).**
> These source/driver investigations remain auditable historical evidence, NOT
> deliverables or blockers for the currently active **Phase 1 IC Information**.
> Do not continue silicon-ID/Erase/Program/Verify or Profile work under Phase 1.
> Phase 1's source-bound exact manufacturer fields and coverage are in
> [NXP_PHASE1_IC_INFORMATION_V13.md](NXP_PHASE1_IC_INFORMATION_V13.md).
> No software `SUPPORTED`, Catalog visibility or hardware HIL claim follows.
>

ADR-0002 scope: **Research only**, one Draft PR #847, no interim merge permission.

### Source-attested facts, no exact device support claim

OpenOCD upstream **v0.12.0** at full commit
`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.
Seven Target Tcl and Driver C blobs remain Git-object locked to the v9 source
registry. v10 Core/Transport/Driver and KL25 manufacturer Exact identity CSVs
are also separately locked by Git blob SHA.

| Cohort | Exact ICPNs | Official exact metadata | Source Flash model | Remaining qualification gate |
| --- | ---: | --- | --- | --- |
| KL25 | 12 | Existing NXP official exact identity, 32/64/128 KiB P-Flash | `kl25.cfg` → `klx.cfg` → `kinetis.c`; KL branch starts with 1 KiB sectors, Flash size/banks dynamically probed via SDID/FCFG1/FCFG2 | Prove exact order code → actual silicon SDID, revision and bank/sector map; review FCF security/protection writes at 0x400; prove requested erase/program/verify |
| LPC844 | 7 | Exact per-part page still source blocked | `lpc84x.cfg` → `lpc1xxx.cfg` → `lpc2000.c`; **driver-recognized** LPC844_201 silicon IDs map to 64 KiB and 1 KiB sectors | Prove each commercial order code → actual Part ID/IAP ROM and geometry; protect unknown-ID abort |
| LPC845 | 8 | Exact per-part page still source blocked | Same path; driver-recognized LPC845_301 family IDs map to 64 KiB and 1 KiB sectors | Same; verify exact silicon ID and IAP requirements |

**Critical safety:** At this pinned source version, unknown LPC `part_id`
in `lpc2000_auto_probe_flash` leads to `exit(-1)`. This is a process
abort and **must not** be hidden as a harmless "unsupported" return.
Kinetis `kinetis_write` enforces/writes Flash Configuration Field
0x400–0x40F, and explicitly guards device-security bits. Program data
containing FCF may be modified or refused; tests and safety review are
required before product-visible software qualification.

**Operation distinction:** Source functions implement **probe, erase,
write** at driver level. Actual exact-SKU erase/program/verify/Read is
**not** established; every P0 row remains software `CANDIDATE` and
`public_catalog_authorized=false`. A ROM IAP auto-detected 64 KiB
LPC family model is **not** the same as a manufacturer-verified 64 KiB
Flash size for each one of the 15 blocked commercial order codes.

### Delivery and reproducibility

- `nxp-27-p0-openocd-source-evidence-v11.json` locks 27-row source,
  provenance and critical geometry/security/unknown-ID source observations.
- `nxp-27-p0-exact-flash-review-v11.csv` lists each Exact ICPN,
  known vs unknown fields, dynamic-geometry assumptions, silicon-ID gaps,
  source safety blockers and required next evidence.
- `nxp_27_p0_flash_evidence_v11.py` independently recomputes all
  source facts from pinned Git blobs and raises on missing or modified
  safety-critical code paths. Negative tests ensure Source → SUPPORTED
  and family Part ID → exact commercial ICPN promotions cannot occur.
- Public Catalog migration belongs to Issue #849. This PR changes neither
  Production manifest nor OpenOCD deployed runtime or Job/Batch/Socket/PPU.
