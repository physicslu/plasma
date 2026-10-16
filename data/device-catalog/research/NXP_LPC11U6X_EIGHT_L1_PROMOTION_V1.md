# NXP LPC11U67/LPC11U68 — eight exact L1 programming candidates

**Proposed, unmerged** from `main=4a61856bc041fde9a443a1c26830fd64385be6cb`. This is one ADR-0002 cross-manufacturer Catalog Level admission transaction, not NXP-specific Product semantics and **not** a provider/physical qualification.

## Scope and customer effect

- 3 exact LPC11U67 and 5 exact LPC11U68 manufacturer material numbers; all eight originally existed only in source-locked Research. Each has a distinct NXP material/12NC observation and explicit ordering Base.
- Canonical Production Manifest adds exactly eight source-backed mapped target routes from `nxp-lpc11u6x-8-commercial-l1-v1.csv`, preserving the 224 existing NXP identities.
- Expected canonical projection **before merge/deploy**: NXP 232 unique identities, exclusively L0=212, L1=20, L2=0, L3=0; Customer IC Selector NXP=20 and Job Picker NXP=0.
- This is a proposed Product Catalog update, not retroactive mutation of the archived 11-material Research file's `production_admitted=false` and `openocd_programming_qualified=false` historical observations.
- `LPC11U68JBD48E` is included, with manufacturer Base `LPC11U68JBD48`, 12NC `935303821551`, LQFP48 and 256 KiB manufacturer-specified Flash. No exact-silicon-revision claim.

## Independently observed OpenOCD source chain

Pinned upstream release v0.12.0, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`:

| Source file | Git blob | Review fact |
|---|---|---|
| `tcl/target/lpc11xx.cfg` | `d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6` | Defines LPC11xx target and includes `lpc1xxx.cfg` |
| `tcl/target/lpc1xxx.cfg` | `70d26d2673900b06c6d5eef8e55b4542103e9e42` | Defines SWD and `lpc2000` flash bank |
| `src/flash/nor/lpc2000.c` | `f12eef7e4ce68fc8830773f6c57da57dfb87d6b8` | Explicit `LPC11U67_1/_2` → 128 KiB and `LPC11U68_1/_2` → 256 KiB switch cases |

Original-source review at pinned GitHub blobs confirms those structures. The retained `nxp-openocd-reverse-target-lock-v1.json` and `nxp-openocd-source-first-wave4-v1.json` retain their original hashes and are checked by the new test.

Manufacturer source: NXP [LPC11U00 Package/Quality](https://www.nxp.com/products/LPC11U00?tab=Package_Quality_Tab) exact material/12NC observations and [LPC11U6X Rev 1.5](https://www.nxp.com/docs/en/data-sheet/LPC11U6X.pdf) Base/order-table evidence. For `LPC11U68JBD48E`, NXP also has a directly accessible [exact material declaration](https://www.nxp.com/webapp/chemical-content/LPC11U68JBD48E.html) with the matching 12NC.

**Custody limit:** the historical manufacturer HTML bytes and NXP original datasheet PDF bytes were not archived in the original Research ledger. Do not claim original-byte replay or lifecycle verification as of any later date. ADR-0002 permits source-observed unambiguous Exact ICPN identity with an explicit custody gap; an unknown source must never be filled by suffix inference.

## Candidate vs qualified

The mapping means a **source-backed plausible programming route** exists. It does **not** prove silicon revision, erase, page/sector geometry, IAP RAM workspace, read/write/verify, reset, security, installation, or real target success. Of note, a legacy comment in `lpc1xxx.cfg` lists older LPC11Uxx Flash sizes up to 128 KiB; the pinned driver has explicit LPC11U68 256 KiB cases. This mismatch must be investigated in L1→L2 provider qualification, not silently treated as already qualified.

The shared ProgrammingQualificationRegistry must derive `catalog_level=1`, `state != SUPPORTED`, `selector_visible=true`, `job_selectable=false`, `execution_authorized=false`. The shared CatalogPromotionFramework must observe `CATALOG_MAPPED_ROUTE` with `MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED`. No NXP-only Level enum, blocker taxonomy, Product API, or visibility rule is introduced.

## Checks / merge boundary

The source-bound tests assert eight exact rows, distinct NXP 12NCs, frozen research Git blobs, exact material-to-Base-to-explicit-driver-case applicability, and L1-only eligibility; vendor runtime registries and manifest digests must reconcile. Unverified aliases or new suffixes stay excluded. Do not merge without explicit owner approval; no claims of HIL PASS or programming authorization.
