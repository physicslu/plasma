# NXP Phase 1/2 — ADR-0002 sole-authority retirement register (2026-10-15)

**Status:** All nonconforming **ACTIVE** NXP Phase 1 / 2 CI research-priority workflows retired in PR #930. Historical source records remain intact for forensic reproducibility. Applicable policy authority is **[ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)**. No extra NXP-specific Stage/Priority enum is permitted in new API, UI, Phase1/2 reports, qualification or Job gates.

## Effective normative execution chain

1. NXP official exact orderable material/source, Base/Family binding → Phase 1 `IDENTIFIED` and independently reported `INFORMATION_COMPLETE`.
2. The sole current NXP Phase 1/2 audit is `nxp_adr0002_phase1_phase2_canonical_v1.py`. It uses **297 distinct confirmed exact ICPNs**, not an unvetted 501-row or 65-discovery research priority pool.
3. Its Phase 2 research states are **CANDIDATE=28** (KL25 12, K32L2 16) and **UNKNOWN=269**. No newly evidenced `SUPPORTED` or `UNSUPPORTED` in this bounded research projection. `SUPPORTED` requires each exact applicable ICPN's silicon/revision, pinned provider/CFG/flash driver, security, geometry, Erase/Program/Read/Verify and approved Programming Profile.
4. Phase 3 **NOT AUDITED**; no PPU, Site, Adapter, Socket or physical HIL certification. All Production Manifest / IC Selector / Job / Batch are unchanged in this PR. Phase 1 Selector visibility is a separate change under Draft PR #927.
5. Mandatory CI: `.github/workflows/device-catalog-nxp-adr0002-phase1-phase2-v1.yml`, with canonical evidence test and single-authority retirement guard. Do not add future alternatives based on P0/P1/P2.

## Retired GitHub Actions CI entrypoints

The following ten `.github/workflows/` files are **deleted** from the active branch; the historical workflow definitions can be recovered from Git history, but no future CI pass/fail may use their historical priority outcomes as active phase qualification:

- `device-catalog-nxp-adr0002-v9.yml`
- `device-catalog-nxp-openocd-reverse-coverage-v1.yml`
- `device-catalog-nxp-source-first-active-v2.yml`
- `device-catalog-nxp-source-first-wave3-v1.yml`
- `device-catalog-nxp-source-first-wave4-v1.yml`
- `device-catalog-nxp-discovery-65-gates-v1.yml`
- `device-catalog-nxp-phase1-funnel-audit-v1.yml`
- `device-catalog-nxp-phase1-lpc11u-lpc83x-11-v1.yml`
- `device-catalog-nxp-phase1-official-lpc25-v1.yml`
- `device-catalog-nxp-phase1-kinetis21-v1.yml`

**Rationale:** Their active tests/dependencies either treat historical P0/P1/P2 quotas as a review gate or transitively invoke historical scripts pinned to an outdated ADR blob / pre-canonical Phase1 snapshot. Those historical states are not legitimate policy authorities under current ADR-0002. Replacing only a label while continuing to gate on that priority count is not sufficient.

## Immutable archival research (NOT deleted)

Keep the original v9-v12, early v13-v1 and 65-wave source CSV/JSON/Python/test assets and their existing source hashes unaltered. They are historical research observations / diagnostic facts and are permitted as *non-normative inputs* to a new review. NXP 501 old research = 224 historically admitted exact + 277 research-only; 65 reverse-wave candidate observations = discovery leads, not Phase2 eligible complete ICPNs. All newly normalized Phase1 material/12NC ledgers remain source-locked, including the 73 additions and associated original manufacturer PDF/HTML-byte custody gaps. The Phase1/2 canonical projection reads old **data** by exact ICPN, not by historical P0/P1/P2 score.

**Do not run legacy scripts as an eligibility/admission gate or as a product status publisher.** Existing archived Python remains callable for forensic replay only; removing original bytes would destroy auditable source evidence and is deliberately out of scope. Any future historical replay must carry a clear ARCHIVE / NOT NORMATIVE label and never write a Production or public status snapshot.

## Remaining remediation backlog

- Phase 1 `INFORMATION_COMPLETE=0` in this strict historical evidence snapshot; 212 old Base values mirror ICPN and need independent Base reconciliation; 73 new manufacturer original binary archives unavailable.
- Phase 1 legacy 277 identities still Research-only; two old reverse leads have identity/order ambiguity. Do not silently promote.
- Phase 2 candidates need exact silicon/revision, CFG/include graph, flash geometry/security/power/reset constraints, qualified operations and a reviewed Programming Profile. K32L2 16 source-backed candidates currently lack verified Target CFG.
- Runtime and current product API should eventually expose all normalized Stage states and metrics uniformly across brands. No such production deployment is made in this PR.

**Merge policy:** PR #930 stays Draft until owner approval and complete CI PASS. This change neither asserts all NXP devices are unsupported nor certifies any new flash programming path.
