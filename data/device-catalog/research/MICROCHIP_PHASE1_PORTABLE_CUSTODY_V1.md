# Microchip ADR-0002 Phase 1 — Portable original-evidence custody v1

**Scope:** portable manufacturer original-byte archive and offline cold replay. **This is NOT deployed durable/offsite custody.**

## Why this exists

PRs #871 and #874 captured official MicrochipDirect MCU chart HTML and original 20/60-paginated Microchip MCP product responses. However their GitHub Actions original-byte Artifacts expire in **90 days**. A SHA-256 reference without its exact original bytes cannot be independently replayed afterward.

This PR ships a standalone, versioned **portable evidence package plus local filesystem handoff verifier**, not a storage server, data admission, authenticity signature, enforceable retention policy or offsite copy.

## What the bundle holds

The bundled scope is exactly the **two new P0 exploratory families** from PR #874, not all historic Microchip research:

- Original official manufacturer chart: chart/original-chart.html and chart/manifest.json.
- MCP original source response bytes, manifests and optional source summaries, separately for E5/D5 and PIC32MX.
- The actual chart-derived plan.json, the original Phase 1 341-row crosswalk report.json, and a canonical bundle-index.json containing per-file original-byte SHA-256 and lengths.

The **packer must independently replay** chart source SHA-256 and P0 family rows, verify the actual manufacturer-chart-selected query names, independently validate the two MCP complete 20/60 pagination streams and response hashes, recompute the Research matrix and compare it with report.json. Only after these checks does it create a ZIP containing byte-identical original evidence; it then **independently extracts the new archive and replays it again**. This is an offline validation, not a network call or a promise of long-term retention.

The bundle is deterministic for identical inputs: fixed ZIP names, ordering, timestamps and attributes, without adding pack-time timestamps to the payload. It rejects unexpected files, secrets-by-unknown-name, nested paths, symlinks, path traversal, duplicate archive paths, suspicious member types, excessive sizes, corrupted hashes, mismatched source-query plans, inconsistent manufacturer responses and attempts to declare unearned durable storage or Production authorization.

## Example commands

Use exact source files created by official checked-in capture scripts or a previously downloaded unmodified CI Artifact. Substitute actual operator-owned paths below.

~~~bash
python data/device-catalog/research/microchip_phase1_portable_custody_v1.py \
  --pack /archive-staging/microchip-p0-evidence.zip \
  --chart-root /original-evidence/chart \
  --e5-root /original-evidence/mcp-e5 \
  --pic32-root /original-evidence/mcp-pic32 \
  --plan /original-evidence/plan.json \
  --report /original-evidence/report.json \
  --receipt /archive-staging/pack-receipt.json

python data/device-catalog/research/microchip_phase1_portable_custody_v1.py \
  --verify /archive-staging/microchip-p0-evidence.zip \
  --receipt /archive-staging/cold-replay-receipt.json

sha256sum /archive-staging/microchip-p0-evidence.zip
~~~

The two JSON receipts explicitly contain:
- source_originals_sha256_replayed = true
- original_mcp_dual_pagination_replayed = true
- source_to_phase1_chart_report_replayed = true
- durable_storage_verified = false
- independent_offsite_copy_verified = false
- production_write_authorized = false

No tool or ZIP file can truthfully assert its own permanent storage. Source authenticity beyond the trusted transport and original capture provenance is not independently digitally signed.

## CI behavior

The CI workflow runs negative/security tests offline, then a **separate best-effort live original MicrochipDirect chart + two bounded official MCP queries**. If live manufacturer access fails, the live step is a recorded failure even if offline unit tests and overall workflow PASS. It only publishes a real portable archive with a cold-replay receipt if both manufacturer query sources pass. The output Artifact **also expires in 90 days**.

Inspect the specific live step outcome, archive and cold-replay receipt; a green GitHub check is not proof of the live source capture. Test fixtures are synthetic and **never** manufacturer data.

## Verified live manufacturer cold-replay result (2026-10-14)

- [CI run 38533403798](https://github.com/physicslu/plasma/actions/runs/38533403798): original MicrochipDirect chart and both bounded P0 MCP queries acquired; **ZIP pack + independent cold restore/replay PASS**.
- [Temporary original-source ZIP and validation receipts artifact 11878554641](https://github.com/physicslu/plasma/actions/runs/38533403798/artifacts/11878554641): **18 original source/report files** in the exported portable bundle.
- ZIP SHA-256 from actual GitHub Runner: **9d9de5ac644b8b9d59f20d343f94bf9a5e964920c96260cabc5461fa747efe2b**. Independent pack and cold-replay receipt comparison **PASS**.
- **Expiration: 2027-01-12 08:11:45 UTC.** This is still an expiring GitHub Actions Artifact, with no separately configured long-term/offsite storage. An immutable/WORM copy and independent restore remain outstanding.
- Validation is scoped to original manufacturer chart + two separate MCP source queries; this is not a validated worldwide SKU inventory or software-programming qualification.

## Operator-controlled local storage handoff (not deployed)

The new `microchip_phase1_local_vault_v1.py` adds three explicit operations against a pre-existing **absolute** filesystem directory; it requires no new web service or credentials. **No SWPC host was contacted or modified in this PR.**

- `--deposit ORIGINAL_ZIP`: replay the original manufacturer bundle, exclusively create an evidence-key directory (never overwrite), stream-copy and fsync the stored file, **cold replay the stored copy**, and publish a receipt only after this passes. An incomplete key is preserved as a failure for operator inspection.
- `--audit`: read from the chosen local store, verify the original bundle again, compare against the stored receipt, reject altered source content, unexpected files and unauthorized claim flags.
- `--restore RESTORED_ZIP`: audit the stored object, exclusively create a new restore output, and independently reverify its original chart and full MCP response pagination evidence.

All receipts explicitly report `durable_storage_verified=false`, `independent_offsite_copy_verified=false`, `immutable_object_lock_verified=false`, `retention_policy_enforced=false`, and `production_write_authorized=false`.

**SWPC example only; paths are illustrative, not asserted to exist.** Provision and run with an account that owns the intended vault, not from a CI GitHub-runner temporary directory:

~~~bash
install -d -m 0700 /storage/plasma-evidence-vault

python data/device-catalog/research/microchip_phase1_local_vault_v1.py \
  --deposit /path/to/downloaded/portable-original-evidence.zip \
  --vault-root /storage/plasma-evidence-vault \
  --evidence-key microchip-p0-20261014-e5-pic32 \
  --receipt /path/to/staging/local-deposit-receipt.json

python data/device-catalog/research/microchip_phase1_local_vault_v1.py \
  --audit --vault-root /storage/plasma-evidence-vault \
  --evidence-key microchip-p0-20261014-e5-pic32 \
  --receipt /path/to/staging/local-audit-receipt.json

python data/device-catalog/research/microchip_phase1_local_vault_v1.py \
  --restore /path/to/independent-restore/microchip-p0-restored.zip \
  --vault-root /storage/plasma-evidence-vault \
  --evidence-key microchip-p0-20261014-e5-pic32 \
  --receipt /path/to/staging/local-restore-receipt.json
~~~

Each external receipt/restore parent directory must already exist and every output name must be new. A local `/storage` path is **not evidence of a different disk, an offsite copy, retention enforcement, disaster recovery, or immutability**.

The updated CI performs **deposit/audit/restore** on the *real manufacturer-sourced* portable bundle inside an ephemeral GitHub Runner directory. It verifies this local code path but neither deploys to SWPC nor retains the resulting evidence beyond the same GitHub 90-day Artifact expiration.

**Residual controls not implemented:** privileged administrators can edit/delete local files; hashes without independently held signed receipts do not prevent malicious coordinated replacement; retention, offsite storage, archive access management, and independent disaster restore are external operator duties.

## Explicit durable storage acceptance gate

Before authorizing a permanent identity Catalog decision, the operator needs:

1. An independently administered destination outside GitHub Actions, with named owner, object/path, source capture date, retention policy, access/deletion permissions and recovery procedure.
2. The ZIP bundle plus its SHA-256, receipts and exact repository/tool commit, copied byte-identically. Prefer protected object versioning/object lock and a second geographically independent copy.
3. A fresh restore **from that destination**, including a SHA-256 check and offline --verify on a separate host. Record archive object/version, validator identity/time and independent replay receipt in a separately governed ledger.
4. Periodic restore/readability checks and expiration alerts. Check manufacturer terms before placing downloaded content in a publicly shared object store.

Only that external restore and retention verification can support a separate owner-approved DURABLE_VERIFIED state. **This PR does not configure those stores or credentials and does not mark that gate complete.** The original package permanently declares durable_storage_verified=false.

## Boundaries and next work

- This v1 bundles only PR #874's **E5/D5 and PIC32MX** current-source query originals. The prior PR #871 SAMD21 originals, earlier official Microchip XLSX/PDF and other vendor source artifacts are **not covered**, and must be migrated before their existing Artifact expiration dates.
- Zero Production ICPN admission, no exact commercial part VERIFIED upgrades, no OpenOCD SUPPORTED, no Phase 2 Programming, no Phase 3 PPU/Socket/HIL/FPGA, no public UI/API changes.
- The 341 chart P0 Base Devices and two cohort source candidates are not a manufacturer-wide commercial-SKU census.

**Open owner decision:** designate a long-lived restricted archive destination, required retention and independent restore operator before deployment.
