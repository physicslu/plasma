# OPF Local Owner Mode — Gate 1 authorization-chain audit and migration ledger

**Owner decision:** 2026-11-09, Local Owner Mode becomes the intended default PPU product policy; [ADR-0008](../adr/0008-local-owner-mode.md) is the normative target.

**Source lock:** `main` at `6706758d5a4ef536d9f02a7df860ccfa3b565b80` (2026-11-09 UTC). This is a **source-only / Host-only** Gate 1 audit, not an implementation or a PPU security qualification. The PR must refresh affected entries if main changes before Gate 2.

**Execution scope:** ChatGPT Direct, documents and Host-only baseline verification. No executable changes to Bootstrap, Manager, BFF, Console, Provider, Runtime or PL; no deployment, controller/SWPC access, PPU/DUT, or merge. Existing guards remain enforced until a separately scoped implementation PR completes its own tests.

## 1. Observed authorization chain

```text
Browser Console Runtime panel / Site configuration
  -> same-origin BFF (Manager routing, conditional maintenance cookie)
  -> Manager registry entry (pending -> commissioned manual transition)
  -> Manager Bootstrap Coordinator (stored alias + device_id + Bearer token)
  -> PPU Bootstrap :18081 (Bearer authentication on POST)
  -> B1 upload / B2 admission / B3 install (SHA/device/action/transaction HMAC)
  -> verified PPU Active Set / PPU Job admission
  -> Site Lease / FPGA fence / SAFE_OFF / outcome journal / recovery
```

The current **one-PPU Console programming flow has real Site 2 evidence** in `docs/evidence/console-bundle-programming-hil-2026-11-09/`, but this does not prove initial enrollment, replaced controller, token recovery, UI cache-miss, other Sites, or Local Owner Mode.

| Area | Observed code / decision point | Current behavior / migration gap | Disposition |
| --- | --- | --- | --- |
| Manager registry | `software/python/plasma_manager/server.py`: `_handle_registry_add`, `_handle_registry_lifecycle_unlocked`, `_registry_lifecycle`; `software/python/plasma_manager/registry.py` | Add creates pending. A fresh trusted fleet observation is required before manual commissioned transition; write endpoints reject uncommissioned PPU. | **Replace human approval** with an automatic identity/topology/readiness reconciliation after trusted enrollment; preserve pending/disabled/conflicted state and durable CAS protections. |
| Manager programming | `software/python/plasma_manager/programming.py`: `_require_commissioned` | Programming controller requires `commissioned`; outcome uncertainty has separate blocking policy. | Replace lifecycle dependency only after the new trusted local-control state is authoritative; retain UNKNOWN no-replay. |
| PPU/Site Console | `software/web/app/engineering/ppu-site-configuration.tsx`, `ppu-runtime-activation.tsx`, `ppu-site-desired-configuration-core.tsx`, `software/web/app/api/manager/ppu/route.ts` | Manual Add / Validate & Enable and commissioned-only UI/API gates. | Unify into `Connect PPU`; leave hardware/session locks at the backend. |
| Bootstrap credentials | `software/python/plasma_manager/bootstrap.py`: `BootstrapCredentialStore`, `ManagerBootstrapCoordinator._authenticated` | Token is scoped to alias + device_id, persisted mode 0600; missing token stops B1/B2/B3. Manager cannot recover without it. | **Replace token acquisition** with physical/local enrollment and a rotatable device-bound key; persist no plaintext in Browser; loss/replacement recovery must not drop PPU journal. |
| Verified pairing | `software/python/plasma_manager/verified_bootstrap.py`: `VerifiedManagerBootstrapCoordinator.pair` | Receives user token, probes protected Bootstrap endpoint and persists after expected rejection. | Retire this human-provided-token API only after equivalent device-authenticated enrollment is implemented and negatively tested. |
| PPU Bootstrap | `scripts/ppu-bootstrap-service.py`: `ServicePaths.token_file`, `provision_token`, `load_token`, `BootstrapHandler._authorized`, `do_POST` | All Bootstrap POST mutation requires device-local Bearer; `provision-token` emits token; no reviewed physical re-enrollment route. | Keep authenticated writes, introduce a physically bounded enrollment/recovery path; preserve B1/B2/B3/journal transaction identity. Do **not** simply remove `_authorized`. |
| Owner operation proof | `software/python/plasma_manager/owner_authorization.py`: `issue_bundle_operation`; `scripts/ppu_owner_authorization.py` | One HMAC per exact device/action/SHA/transaction from paired credential. No per-Bundle manufacturer whitelist. | **Retain** internal proof, rotate its device-secret derivation with enrollment; never expose or require a manual operation token. |
| Console deployment | `software/web/app/engineering/ppu-runtime-deployment.tsx` | `pairingToken` field and `Authorize Platform Maintenance` button; B3 controls depend on `pairing.paired` and device match. | Remove user token UI **after** P2. Keep explicit install/activate/FPGA-load user intent and receipt presentation. |
| Browser capability | `software/web/app/api/manager/maintenance-capability.mjs`, `bootstrap-bff.ts`, `registry/[...path]/route.ts` | `mutable` Registry policy returns capability configured/allowed without cookie; `fixed-lifecycle` requires HTTPS Origin and 15-minute HMAC cookie after pairing. | Local Owner default does not add a cookie/HTTPS gate; retain same-origin BFF, local binding and route allowlist. Separately retire fixed-lifecycle logic only after consumer audit. |
| Optional secure Gateway | `docs/architecture/remote-write-security-boundary.md` | Existing opt-in Principal/role/Site-scope secure-write architecture, not required for local PPU execution. | Do not force a human login in Local Owner Mode. Audit actual deployment profile and direct Gateway access before removing any remote-write guard. |
| OPF Core | `docs/architecture/opf-architecture.md` and merged standalone Provider boundary | Portable OPF intentionally has no mandatory PPU/Bundle/HMAC dependency. | **No core change**. This is PPU Host / control-plane policy. |
| PPU / PL safety | `docs/architecture/ppu-execution-ownership.md`, `scripts/ppu_site_worker_service.py`, `scripts/ppu_owner_authorization.py`, ADR-0007 | Job concurrency, Site/PPU fences, SAFE_OFF/SEALED, uncertain outcomes are separate from user enrollment. | **Preserve**. Validate independent hardware fail-safe before claiming arbitrary custom bitstream safety. |

## 2. Security decisions before the first implementation PR

1. **Presence evidence:** determine whether a PPU-owned physical button, jumper, USB/UART local console or other true direct-access channel is available and can be bound to one enrollment session. A same-LAN HTTP request does not suffice. PYNQ-Z2 is a prototype; specify a product-wide PPU contract, with Z2-specific adaptation only underneath.
2. **Transfer protocol:** define `UNENROLLED`/`ENROLLED`/`RECLAIM_PENDING` state, anti-replay nonce and deadline, atomic key rotation, device identity and authenticated rebind. Specify what happens to the first Manager and any executing Job. No untrusted request can induce key reset or `READY`.
3. **Local network scope:** bind Console/BFF and Manager to loopback; prefer a dedicated/isolated PPU interface or an authenticated management channel. Direct Bootstrap service must not be write-open to general LAN, even for a moment during recovery.
4. **Safe continuity:** credential loss and Manager restart never clear `OUTCOME_UNKNOWN`, active Set SHA, SEALED, Root Source/Boot identity, Site Lease or pending B3 receipt. An ambiguous installation is reconciled, not reissued.
5. **FPGA caveat:** enumerate which outputs/power gates are controlled independently of arbitrary PL images; neither SHA256 nor self-described ABI is an electrical safety guarantee. If independent fail-safe is absent, custom-image activation remains hardware NO_GO until a qualified mechanism exists.

## 3. Minimal implementation PR decomposition (not authorized in this PR)

| PR | Domain | Minimal change | Required negative evidence |
| --- | --- | --- | --- |
| LOM-P2A | PPU Bootstrap + Manager enrollment | Device-side physically bounded enrollment/restore API, local-generated credentials, device-bound Manager persistence/rotation | LAN takeover rejected; replay/expired enrollment rejected; wrong device; lost key; concurrent Manager; crash/rollback; in-flight/UNKNOWN preserved |
| LOM-P2B | Manager Registry | Trusted observe-and-connect admission, durable readiness reconciliation, explicit multi-controller collision | Spoofed identity/topology, stale observation, duplicate alias/endpoint, Manager restart, persistence/CAS failure |
| LOM-P1 | Console/BFF | One Connect PPU flow, remove token input and manual enable for Local Owner, truthful readiness states | Direct REST bypass, wrong origin, loopback exposure, read-only LAN cannot write, pending recovery not shown as READY |
| LOM-P3/P4 | Maintenance + programming | Internal auto-issued transaction proofs for Runtime/Bundle/Provider/FPGA, remove dead UI/branches, comprehensive regression | SHA/Target/ABI mismatch, unsafe PL/voltage, busy Lease, B2-to-B3 action swap, `OUTCOME_UNKNOWN` and no-replay |

Do not create a parallel deployment engine, extra OPF Router or per-Package manufacturer allowlist. Preserve the existing Bundle v3 B1/B2/B3 implementation. Replace-by-Default applies only **after** the replacement is implemented and proven.

## 4. Gate 1 Host-only baseline and future acceptance matrix

`PASS` below may only describe an **actually run** test on this PR HEAD. The scenario cases for newly proposed features are `NOT_IMPLEMENTED` / `NOT_RUN`, not XFAIL-as-PASS.

**Observed local Host-only baseline on this documentation-only branch (Python 3.12.14 / pytest 9.2.0):**

```text
software/python/.venv/bin/python -m pytest -q \
  tests/test_manager_bootstrap_verified_pairing.py \
  tests/test_manager_bootstrap_rest.py \
  tests/test_ppu_owner_authorization_gate1.py \
  tests/test_manager_runtime_registry.py \
  tests/test_render_control_station_security.py

PASS: 76 tests, 18 subtests; exit code 0 (20.00 s)
```

This executes current authentication and safety regressions, **not** the future Local Owner functionality. Python emitted a `pytest-asyncio` deprecation warning about its fixture loop-scope default, not a test failure. The documentation-integrity guard separately reported `PASS (700 Markdown files)` with exit code 0 after adding the two new documents.

| Scenario | Test / evidence source | Gate 1 status boundary |
| --- | --- | --- |
| Current token verification and wrong-token rejection | `software/python/tests/test_manager_bootstrap_verified_pairing.py`, `test_manager_bootstrap_rest.py` | Baseline regression only; **not** no-token enrollment |
| Current HMAC B2/B3 exact action/SHA/device and negative cases | `software/python/tests/test_ppu_owner_authorization_gate1.py` | Baseline integrity regression only |
| Current registry lifecycle, restart and reject behaviors | `software/python/tests/test_manager_runtime_registry.py` | Existing manual lifecycle regression only |
| Browser capability mutation/origin negative policies | `software/python/tests/test_render_control_station_security.py` and current Web tests | Current opt-in/fixed profile safety only |
| First-time physical/local enrollment with no manual token | Not implemented | **NOT_RUN** |
| Replacement computer and lost prior token without manufacturer assistance | Not implemented | **NOT_RUN** |
| Concurrent Manager collision / malicious LAN control takeover | Not implemented | **NOT_RUN** |
| New flow Manager restart + no-leakage persistence | Not implemented | **NOT_RUN** |
| User-developed Provider/FPGA safe admission without manufacturer allowlist | Partly existing Bundle v3; new local owner boundary not implemented | **NOT_RUN** for Local Owner E2E |
| Custom FPGA bypass of SAFE_OFF, wrong voltage or ABI | Hardware threat analysis pending | **NOT_RUN** (Host-only cannot prove electrical safety) |
| `OUTCOME_UNKNOWN` blocks automatic resend after re-enrollment | Existing PPU safety; local re-enrollment not implemented | **NOT_RUN** for new flow |

**Exit criteria for Gate 1:** ADR accepted as target; source-linked change ledger and safety exclusions reviewed; existing focused Host-only baseline tests actually run and reported; new Local Owner positives/negatives defined for later PRs; docs integrity passes. This docs-only PR cannot claim Local Owner Mode functional PASS or authorization migration complete.

**Next Gate:** independent Gate 2 approval to merge the specification PR after CI, reviews, threads and mergeability are checked. A later implementation still requires a bounded Gate 1 before executable work or hardware validation.
