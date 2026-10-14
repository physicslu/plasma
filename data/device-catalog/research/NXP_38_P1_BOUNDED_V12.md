# NXP P1 (38 exact) — one bounded OpenOCD v0.12.0 source check completed

**ADR-0002 stop rule:** P1 is a single scope-budgeted source inquiry, NOT
a standing instruction to research every exact NXP commercial SKU.

All 38 P1 ICPNs in the v10 501-row source-locked Core/Transport/Driver
ledger were reviewed at pinned upstream commit
`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`:

- LPC802/804 **18**: pinned generic `lpc8xx.cfg` includes
  `lpc1xxx.cfg` and `lpc2000` Flash bank, yet the pinned driver
  auto-detection table does not enumerate explicit `LPC802_` or
  `LPC804_` IDs. Other generic code may exist; lack of this explicit
  enumeration is **not proof of permanent incompatibility**. Exact
  orderable-part applicability and program/erase/verify are **unproven**.
- K32L2 **20**: `kinetis.c` is a research lead; the inspected pinned
  `kinetis.c` and `kinetis_ke.c` have no explicit `K32L2`
  identity, and no dedicated basename `k32*.cfg` is present in pinned
  `tcl/target/`. Generic Kinetis Target reuse is still possible but
  **not verified for these 20 exact commercial ordering codes**.

Thus **38/38 stay P1 CANDIDATE**, with
`COMPLETED_FOR_PINNED_COMMIT` and an explicit **park / reopen gate**.
Reopen only on source/version changes, new official exact
silicon-to-driver evidence, or owner-approved customer/product scope.
No automatic reassignment to UNSUPPORTED, EOL, P0 or SUPPORTED.

Evidence is original pinned Source + Git blob checks and
`nxp-38-p1-one-pass-v12.csv` per-part negative ledger. Source-level
Flash callbacks do not prove an executable installed OpenOCD or real
device erase/program/verify. Production Identity Store, public Catalog,
Job/Batch, PPU, Site and Socket remain unchanged.
