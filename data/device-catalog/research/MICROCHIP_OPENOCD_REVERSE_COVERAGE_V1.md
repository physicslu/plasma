# Microchip Phase 1 — OpenOCD CFG-first reverse ICPN coverage v1

**Decision:** research only **OpenOCD Target CFG → manufacturer Base Device → exact ICPN**, then publish a three-field read-only `ICPN → Base Device → Target CFG` report. **Flash Driver, algorithm compatibility, runtime flash commands, Production Catalog, PPU/FPGA/HIL and public IC Selector are out of scope.**

## Why inversion is faster

Do not rerun 24,051 commercial ICPN name regexes against individual CFG files. The source-pinned OpenOCD 0.12.0 Research lock already contains **9 P0 CFGs** and **2 P1 target-only CFGs**. Classify the original manufacturer DFP Device Support Names *once per CFG* to form an indexed lookup, then join the original manufacturer MCP `basePartNumber` values for commercial ICPNs. The output is always three visibly separate fields. No automatic substring truncation, suffix guessing or generic family-based claim of per-SKU programmability.

Version lock: OpenOCD `0.12.0`, commit `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. Source lock: `microchip-openocd-first-source-lock-v1.json`.

### Distinct source population boundaries

| Source and unit | Frozen count | Meaning |
| --- | ---: | --- |
| Existing Research manufacturer MCP commercial ICPN candidates | 24,051 | Historic source-linked candidates, **not** the number mapped by this script |
| Original archived Microchip DFP device support names | 3,717 | Vendor tool-support names, **not** exact commercial ordering codes |
| DFP names in P0 CFG research group | 364 | Source-locked research **CFG leads**, not 364 supported SKUs |
| DFP names in P1 CFG-only group | 12 | No corresponding Flash Bank source proof in this screening |
| DFP P2 archive-only names | 3,341 | Not screened by this bounded CFG set; **not** proven unsupported |
| Original manufacturer chart 32-bit MCU Base Devices | 703 | Separate chart source, with 341 P0 names |
| This specific current source-replayed MCP pilot | 24 | Two Base Devices, E5/D5 (10) and PIC32MX (14); **not** 24,051 ICPNs |

A frozen aggregate is never used to synthesize DFP names or per-ICPN CFG mappings. Without the exact DFP **original index.html + manifest.json**, the tool reports only nine P0 and two P1 CFG leads and leaves exact commercial-ICPN coverage **null**.

## Join rules

1. **CFG side first**: validate `release/openocd.json`, the locked OpenOCD Target CFG Git blob identity and manufacturer DFP original HTML digest. Reproduce the frozen 364 P0 / 12 P1 groups, with all individual DFP device names and source pack identifiers.
2. **Manufacturer commercial identity**: for each exact ICPN, use independently linked MCP `partNumber`, `basePartNumber`, `query` and original response SHA-256. An original MCP `basePartNumber` can differ from the DFP device name.
3. **Exact-name join preferred**: only identical DFP name ↔ original MCP `basePartNumber` is a candidate by default. The single separately reviewed exception is `ATSAMD21G18` (MCP Base Device) ↔ `ATSAMD21G18A` (DFP name), requiring original MCP query `ATSAMD21G18A`. No other suffix heuristic is permitted.
4. A CFG is recorded as `EXACT_DFP_NAME_CFG_CANDIDATE`, `REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE`, or `P1_TARGET_ONLY_CFG_CANDIDATE`. Missing Base Device, conflicting MCP bases, no DFP match and unqueried exact ICPN stay separately `UNKNOWN`/unresolved. **P1 target-only is not treated as flash support**.
5. Exact ICPN rows must never claim `software_supported`; availability of CFG text alone cannot prove silicon identity, revision compatibility, Flash geometry or operation success. The report does not expand or edit the Production Catalog.

The optional `--mcp-rollup` accepts a *previously generated*, source-linked Microchip raw batch ledger. That **derived JSON input** is **not revalidated against manufacturer original bytes in this particular command**. The output marks `all_icpn_original_bytes_replayed_in_this_command=false` even if its source link hashes are present. A fully sourced recheck requires invoking the original rollup source-replay pipeline or the bounded ZIP option below.

## Real original-source path (read-only)

A dedicated CI workflow consumes the existing official DFP original-byte Artifact from run `38338847345` and the latest stable two-query original chart/MCP portable ZIP from run `38535507957`.

That ZIP is independently verified using `microchip_phase1_portable_custody_v1.py`, then the manufacturer chart/MCP crosswalk is regenerated. This checks **only the two current pilot Base Devices and their 24 source-observed ICPNs**, not all historical 24,051 candidates.

From a repository checkout after downloading both unmodified original-source archives:

~~~bash
python data/device-catalog/research/microchip_openocd_reverse_coverage_v1.py \
  --dfp-evidence-root /path/to/original-microchip-dfp \
  --portable-bundle /path/to/original-portable-evidence.zip \
  --output /tmp/microchip-reverse-cfg-icpn.json

python data/device-catalog/research/microchip_openocd_reverse_coverage_v1.py \
  --dfp-evidence-root /path/to/original-microchip-dfp \
  --portable-bundle /path/to/original-portable-evidence.zip \
  --output /tmp/microchip-reverse-cfg-icpn.json --verify
~~~

The report contains **per-CFG device-name rows**, **per-ICPN three-field rows**, precise **mapping status**, original response SHA-256 source reference and grouped counts. All fields related to production/silicon/programming qualification remain false. CI reports the actual join coverage after downloading and revalidating the original bytes. If any original archive is missing, expired, changed or inconsistent with the pinned DFP snapshot, the live mapping must **fail**, not silently show an invented zero.

## Complete historical source sweep — actual independent replay (2026-10-15)

[CI run 38664576255](https://github.com/physicslu/plasma/actions/runs/38664576255) fetched **the official original Microchip DFP index, the 16-batch MCP original research archive and 12 disjoint original MCP shard archives** from GitHub Actions. It did not issue new vendor network searches. All 13 source roots and their original response bytes were independently replayed using the established Microchip original-source replay validators, frozen DFP query plan and original-response SHA-256 checks.

- **321** original batch directories existed: **313** had valid source attestation and **8** were quarantined. Preserve this distinction; the archived original batch count is not the count of validated batches.
- Manufacturer source queries: **2,753** positive exact-prefix, **68** completely replayed zero-prefix, **297** source NOT_FOUND and **80** timeout/unverified (the latter two must not be reclassified as zero commercial products).
- Historical source audit counted **23,427 raw source-linked candidate observations**; exact-ID-deduplicated replayed output has **23,276 original manufacturer commercial ICPN candidates**. The deduplicated per-ICPN output preserves **23,276 source-link references**, not the pre-dedup observation-event count. Do not merge these denominators.
- **CFG-FIRST candidate mapping** of the 23,276 original-source-replayed ICPNs: **2,414** exact MCP Base Device ↔ DFP Device Name matches, **23** reviewed manufacturer SAMD21 Base/DFP alias candidates, **126** P1 target-only CFG candidates, and **20,713** with no match to the current DFP-name/CFG Research index. Therefore: **2,437 P0 candidate mappings**, **126 P1 candidates**, **2,563 total candidate mappings**, and **20,713 unresolved mappings**.
- CFG distribution: `at91samdXX.cfg` **667**, `atsame5x.cfg` **354**, `atsamv.cfg` **175**, `pic32mx.cfg` **1,241**, and P1 target-only `atsaml1x.cfg` **126**. These are order-code candidates, not qualified Flash/erase/write support. Other CFG groups had zero matched commercial order codes **in this specific reconstructed original-source subset**, not proof of zero supported ICs.
- Result and per-ICPN Research matrix: [full original-byte source replay Artifact 11940412265](https://github.com/physicslu/plasma/actions/runs/38664576255/artifacts/11940412265), expires **2027-01-13 01:14:41 UTC**. Separate [bounded 24-ICPN source cohort Artifact 11940521869](https://github.com/physicslu/plasma/actions/runs/38664576255/artifacts/11940521869) also passed.
- **24,051** is a separate historical Research aggregate, not an independently established, identical population denominator to the **23,276** exact-source-replayed order codes. Do not subtract the two and call the difference a verified unsupported or missing set. Microchip-wide manufacturer commercial identity census is unknown.

Run the same original-byte replay locally with all 13 disjoint source roots, never with a copied summary alone:

~~~bash
python data/device-catalog/research/microchip_openocd_reverse_coverage_v1.py \
  --dfp-evidence-root /path/to/official-dfp-original \
  --original-batch-source original-16-batches=/path/to/original-16-batches \
  --original-batch-source shard-0=/path/to/shard-0 \
  ...   --original-batch-source shard-11=/path/to/shard-11 \
  --output /path/to/research/microchip-reverse-all-icpns.json
~~~

The operator must supply **every shard from 0 through 11**, even where a shard is partially quarantined; the script will reject an incomplete set. The `...` line above is a documentation abbreviation for the other numbered shard flags, not shell-executable syntax. The actual GitHub Actions workflow demonstrates the complete executable command.

## Next stage, separately reviewed

Provide an original-source-replayed full Research MCP rollup, including actual `basePartNumber` per ICPN, to map the larger candidate population through this same **CFG-first index**. Record `SOURCE_NOT_AVAILABLE`, `NO_DFP_NAME_CFG_CROSSWALK` and per-CFG candidate counts separately. Only after a reviewer confirms the true rollup population and unqueried remainder should the dashboard show a coverage percentage.

**This PR does not admit new Production ICPNs, change actual target programming, add Flash Drivers, modify PLASMA runtime, or publish UI changes.**
