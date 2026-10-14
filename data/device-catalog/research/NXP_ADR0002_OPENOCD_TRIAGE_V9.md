# NXP ADR-0002 — OpenOCD-first 501 Exact ICPN triage v9

Single research batch on Draft PR #847, one final owner approval. Retains the 277 v8 manufacturer records as historical research. No Production Manifest, public Catalog filter, runtime, Job/Batch, OpenOCD binary, PS/PL or HIL changes.

OpenOCD version is pinned by release/openocd.json to upstream v0.12.0 and commit 9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c. All seven Tcl/C source files have pinned Git blob digests verified from independently checked-out upstream bytes in CI.

| Research priority | Exact groups | Count | Required remaining evidence |
| --- | --- | ---: | --- |
| P0 | KL25 (12) | 12 | Exact SDID/Flash geometry/security, erase/program/verify operation and version scope |
| P0 | LPC844 (7) + LPC845 (8) | 15 | Explicit LPC844/LPC845 IDs in lpc2000.c, but exact orderable variants / IAP/geometry/verify still pending |
| P1 | LPC802 (9) + LPC804 (9) | 18 | Generic lpc8xx driver exists but explicit LPC802/804 ID cases are absent, one bounded check only |
| P1 | K32L2 | 20 | Kinetis driver is a clue, but exact K32L2 target/bank/geometry are not verified |
| P2 | MCX (241), LPC55 (97), KW45 (30), i.MX RT (68) | 436 | Preserve source only; no matched pinned programming path established |
| **Total** | 501 bounded Active exact | **501** | P0=27, P1=38, P2=436 |

Research priority P0 does NOT equal openocd_software_support=SUPPORTED. P0/P1 are CANDIDATE; P2 UNKNOWN (not UNSUPPORTED or EOL). All 501 remain unqualified for new user-facing inclusion by this ledger; 224 previously admitted internal Production identities remain unchanged. The separate ADR public Catalog migration is Issue #849.

Stop rule: do not resume per-part LPC55 PDF acquisition, broad NXP lifecycle searches, MCX device deep datasheet enrichment or socket plans for P2 unless pinned OpenOCD source changes, business demand is evidenced, or the owner explicitly overrides. Only P0 deep exact proof and a single bounded P1 pass are prioritized.

CI must independently compare the original pinned 224 and 277 CSV blobs, pinned OpenOCD Tcl/C blobs, and reproducibly replay byte-identical 501-row triage. NO HIL pass, OpenOCD installed binary, target flash operation or software qualification is claimed.
