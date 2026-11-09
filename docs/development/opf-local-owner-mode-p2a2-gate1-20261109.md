# LOM-P2A-2 Gate 1 report — PS-GPIO button / Engineering CLI enrollment / Recovery-Gated Takeover / G13

> Status: **Gate 1 implementation, Host-only.** Owner approval 2026-11-09 covers code, Host-only tests and a Draft PR only. **Not merged, not deployed; no SWPC/Z2 restart, no DUT, no wiring, no button test, no real enrollment.** Every hardware item below is NOT_RUN.
> Policy: [ADR-0008](../adr/0008-local-owner-mode.md). Contract: [P2A-0 enrollment spec](opf-local-owner-mode-p2a0-enrollment-spec.md) (amended here). Previous step: [P2A-1 request authentication](../deployment/ppu-bootstrap-request-authentication.md).

## 1. Hardware read-only check (documents only)

Sources: TUL PYNQ-Z2 schematic R12 (pages 4, 10, 12), PYNQ v3.0.1 / v2.7.0 board build files (`boards/Pynq-Z2`, `pynqz2.tcl`), Linux `gpio-zynq.c`.

| Claim | Result | Evidence |
| --- | --- | --- |
| Arduino power header is J7; pin 6 = `AR_RST`; pins 2 and 3 = GND | CONFIRMED | Schematic p4 (pin 5 = 3V3, pin 4 = 5V0, pin 7 = IOREF 3V3, pin 8 NC) |
| `AR_RST` = PS `MIO12` (bank 500) | CONFIRMED | Schematic p10 `PS_MIO12_500 D9 AR_RST` |
| Bank 500 = 3.3 V | CONFIRMED | Schematic p12 `VCCO_MIO0_500` on VCC3V3; tcl `PCW_PRESET_BANK0_VOLTAGE LVCMOS 3.3V` |
| On-board pull-up | CONFIRMED | R236 10 kΩ to VCC3V3; tcl `PCW_MIO_12_PULLUP enabled` |
| Shared reset circuit | `AR_RST` is the **output** of open-drain buffer Q9 (NC7WZ07) driven by `PS_RST` (= `PS_SRST_B`, SRST1 button) | Pulling `AR_RST` low cannot reach `PS_SRST_B`, `PS_POR_B` or `PROG_B` (schematic reasoning; **not measured**). Pressing SRST1 also pulls MIO12 low, while the PS is in reset |
| Stock image pinmux | MIO12 = GPIO `inout`, no SPI/I2C/UART/SD/CAN/TTC use; no PYNQ library uses it | `pynqz2.tcl` MIO table; PYNQ source search |
| Linux line | `zynq_gpio` chip (118 lines), MIO n = line n → line 12 | `gpio-zynq.c` |

Electrical: a normally-open button between J7-6 and J7-2/3 is safe **only while MIO12 is an input** (Q9 is open-drain, so no contention). The engine only ever writes `direction=in` and verifies it, never drives the line.

**Not verifiable from documents (Gate 2 hardware step):** that the Z2's BOOT.BIN/`ps7_init` is the stock BSP (read `MIO_PIN_12` SLCR register), the live gpiochip label/base and that line 12 is unclaimed (`gpioinfo`, `/sys/kernel/debug/gpio`, `/proc/device-tree`), the idle level, and the board revision. Until then the shipped profile `scripts/ppu-board-profiles/pynq-z2-enrollment-button.json` is **`enabled: false`** and the button entry is inert.

## 2. What was implemented

| Area | Implementation |
| --- | --- |
| Shared protocol (stdlib, Py 3.10) | `scripts/ppu_local_enrollment.py` (byte-identical Manager mirror `software/python/plasma_manager/local_enrollment.py`): ticket parse/ID/key, claim MAC, credential wrap, pure-Python X25519 (RFC 7748 vectors) and the button window key |
| One enrollment engine | `scripts/ppu_controller.py` `EnrollmentEngine`: SD boot consumption, Engineering CLI arm, button request/contention/press binding, challenge/claim, lost-response retrieval, lockout, Recovery-Gated Takeover, recovery actions |
| Durable records | `ControllerStore`: `controller` / `ledger` / `pending` / `reconciliations`, root-private `0600`, temp+fsync+rename+dir-fsync, cross-process flock; generation high-water ⇒ `FAULT` on a restored record; P2A-1 `control-token` → generation 1 migration |
| Transition fence | `TransitionFence` (writer-preferring RW lock): every admission (Bootstrap mutation, Gateway write) shared; claim / recovery commit exclusive |
| PS-GPIO button | `ButtonProfile` (root-owned board profile), `LongPressDetector` (debounce, hold, release-before-arm, no fire on a release sample), `SysfsGpioInput` (chip by label, forced/verified input), `ButtonWatcher` thread in the Bootstrap service, only when the profile is enabled |
| Engineering CLI | `scripts/ppu-enroll.py` (`arm`, `boot-consume`, `status`); `arm` requires root **and** `engineering_mode_authorized()` on a root-owned, not group/other-writable, unexpired `plasma.ppu.engineering-mode.v1` policy |
| Bootstrap | `scripts/ppu-bootstrap-service.py`: controller-record authentication (P2A-1 MAC unchanged), `/v1/enrollment/{button-request,challenge,claim}`, `/v1/controller/recovery`, `controller_generation` in `/v1/auth/challenge`, controller status in `/v1/status`, per-POST operation classification, admission socket + button watcher at `serve` |
| PPU safety observation | `PPUSafetyProbe`: Bootstrap deployment thread/record/journal, Runtime execution lease (control socket), FPGA reload fence (`LOCK_SH|LOCK_NB`, never blocks a loader), Site seal markers; unobservable state ⇒ recovery blocker |
| G13 Gateway | `software/python/plasma_web/controller_admission.py` mixin in front of `Phase3RouteHandler`; `--controller-admission-socket` (PPU unit) or explicit `--host-lab-unauthenticated-writes`; no default |
| Manager | Credential store schema 2 (`generation`, `controller_id`, v1 migrated in place), `check_challenge` (higher generation ⇒ `ControllerReplacedError`, no retry; lower ⇒ stop), `enrollment` (button start/claim, ticket), `recovery_action`, `PPUHttpClient.write_signer` used by relay, PS loopback, OpenOCD, programming Job and network commissioning; an alias without enrollment is relayed unsigned so the PPU (the enforcement point) refuses it — `503 CONTROLLER_NOT_ENROLLED` or `401 CONTROLLER_UNAUTHENTICATED` |
| Console/BFF | `enrollment` replaces `pair`; Console shows **Enroll with PPU Button / Complete Enrollment** and a development ticket field; no pairing token |
| SWPC CLI / labs | `plasma_program.py` signs its Job; Path 2 baseline reads the controller record; z2like QEMU target installs a 7-day Engineering Mode policy and demo scripts claim engineering tickets |

### 2.1 Button race analysis

* Requests before the press: at most one key per 120 s window. A second distinct key destroys all requests and the window stays `CONTENDED` until it ends; the press then arms nothing. No station is ever chosen between competitors.
* After the press: the window is bound to `request_id` and an ephemeral PPU key; the claim MAC and the credential wrap need the X25519 secret that only the requester holds. Other claims fail and five failures destroy the window.
* While armed: new requests fail `ENROLLMENT_BUSY`; engineering arm fails `ENROLLMENT_BUSY`.
* **Residual (owner decision required):** an *active* man-in-the-middle on the management link at the moment of the press can substitute keys (no PPU display for comparison). Passive observers learn nothing. The Engineering CLI and SD entries are not affected. This is not claimed as solved; it matches the already NOT_QUALIFIED confidentiality of this link. Options for a later gate: LED short-authentication pattern on a PL LED, press-count code, or accept for an isolated management link.

## 3. G13 — Gateway `:18080` mutating endpoint inventory

The deployed Gateway (`gateway_phase3.Phase3PlasmaWebHandler`) has only `POST` writers (no `PUT`/`DELETE`/`PATCH`; the base server answers 501). Classification uses the same predicates the handlers dispatch on.

| Route | Class | RECOVERY_ONLY |
| --- | --- | --- |
| `/api/jobs` | `site.job.submit` | denied |
| `/api/jobs/<id>/cancel` | `site.job.cancel` | denied |
| `/api/settings/sites/<n>` | `site.settings.write` | denied |
| `/api/settings/sites/activation` | `site.activation` | denied |
| `/api/settings/gateway`, `/api/settings/ppu-network`, `/api/settings/ppu-network/activation`, `.../activation/<id>/commit`, `/api/mock/runtime` | `ppu.settings.write` | denied |
| `/api/engineering/diagnostics/loopback`, `/api/engineering/diagnostics/openocd-control-plane`, `/api/engineering/session`, `/api/engineering/targets/<f>/<p>/api/...` | `engineering.write` | denied |
| any other `POST` (incl. `/api/batches*`, not implemented by the PPU Gateway) | unclassified | **403 `CONTROLLER_OPERATION_UNCLASSIFIED` before the body is read** |
| `GET /api/auth/challenge` | read-only challenge proxy | — |

Admission sequence per write: header → admission socket (`admit_header`, nonce consumed) → bounded body → `admit` (record re-read, MAC over method/target/body SHA256, mode policy, fence held shared) → dispatch → response MAC via `sign_response` → connection close ends the hold. Generation is never accepted as a credential. No session or cache exists, so a takeover revokes the old controller on its next request. Without the socket the Gateway answers 503; the deployed unit (`ppu-z2-installer-core.py`, runtime manifest `ppu-runtime.py`) always passes `--controller-admission-socket /run/plasma-bootstrap/controller-admission.sock`.

Manager surfaces that write to the Gateway and are now signed: managed relay (`server.py`), Platform PS loopback and OpenOCD control plane (`bootstrap_server.py`), Bundle programming Job (`programming.py`), network commissioning (`network_commissioning.py`). SWPC CLI: `plasma_program.py`.

## 4. Recovery-Gated Takeover (B3 (b))

| PPU state at a valid claim | Result |
| --- | --- |
| Active Site Job (Runtime execution lease busy), Bootstrap deployment thread/record in flight, FPGA reload fence held, or an in-flight write admission (fence not obtainable in 10 s) | `TAKEOVER_DEFERRED_ACTIVE_OPERATION` with the list; nothing written; window stays armed |
| Site seal marker, unreconciled Bootstrap `recovery_required` deployment (OUTCOME_UNKNOWN), Coordinator journal not in a safe state, or an unobservable lease/fence/seal directory | Commit in `RECOVERY_ONLY` with `recovery_blockers`; old controller revoked |
| None of the above | Commit in `NORMAL` |

Recovery actions (explicit `explicit_request: true` each time): `site.diagnose` / `site.recover` invoke the existing Embedded seal procedure `ppu_site_recovery.py` (it moves the marker into its evidence directory only after its own preconditions incl. SAFE_OFF); `outcome.reconcile` appends a decision to `reconciliations` (the original record is untouched); `recovery.complete` re-evaluates under the exclusive fence and changes only the mode. Nothing cancels, re-sends, clears or rewrites Jobs, journals, seals, Active Set, Boot IDs, leases, SAFE_OFF or evidence. A reconciled Bootstrap OUTCOME_UNKNOWN does **not** relax the existing Bootstrap deployment admission, which still requires its own recovery.

## 5. Deletion Ledger

| Removed / replaced | Replacement | Why safe |
| --- | --- | --- |
| `ppu-bootstrap-service.py` `provision_token`, `load_token`, `_valid_token`, `ServicePaths.token_file`, `provision-token` subcommand | `ControllerStore` + enrollment engine; one-shot `migrate_legacy_token` | P2A-1 file migrates to generation 1 with the same secret; no other producer existed |
| `VerifiedManagerBootstrapCoordinator.pair` and Manager route `/bootstrap/pair` | `enrollment` (button / ticket) | Only callers were the BFF, Console and QEMU demo scripts, all migrated |
| BFF `pair` action, Web `pairManagerPpuBootstrap`, Console "Platform Maintenance Pairing Token" input | `enrollment` action, `enrollManagerPpuBootstrap`, Local PPU Enrollment panel | Contract tests updated |
| `software/python/tests/test_manager_bootstrap_verified_pairing.py` | `test_lom_p2a2_gateway_g13.py` enrollment positives/negatives | Tested the retired manual-token flow only |
| Reference model `serial-dev` source / `serial_arm` / `PermissionError` | `engineering-cli` / `engineering_arm` / `ENGINEERING_MODE_NOT_AUTHORIZED` | Spec amended in lock-step |
| `ppu_package_action.py` `TOKEN_FILE` / `PLASMA_BOOTSTRAP_TOKEN` | `CONTROLLER_RECORD` / `PLASMA_BOOTSTRAP_CONTROLLER` | Same credential, now revocable |
| Path 2 remote read of `control-token`; QEMU `provision-token` / `cat control-token` | controller record; Engineering CLI ticket | Lab/engineering paths only |

Not deleted (owner decision needed): the opt-in Bearer-principal Gateway (`secure_gateway.py`, `secure_gateway_app.py`, `gateway_security.py`, `scripts/plasma-security-deploy`) — a separate SWPC user-level launcher, not used by the PPU unit, but a second Gateway authorization model; the legacy-token migration code — required until every deployed PPU has migrated.

## 6. Compatibility and rollback

* **Synchronized deployment required** (not authorized here): Bootstrap (engine, admission socket), PPU Runtime (Gateway with `--controller-admission-socket`) and the SWPC Manager/Console must move together. Old Manager → new Gateway: unsigned writes 401/403 (fail closed). New Runtime without new Bootstrap: Gateway writes 503. New Bootstrap with old Runtime: Gateway writes stay unbound (G13 inactive) — do not deploy this combination.
* **Gateways without a PPU Bootstrap** (SWPC simulated `swpc-ppu`, QEMU/network host labs) must run with `--host-lab-unauthenticated-writes`; the SWPC configured-mock drop-in (`plasmactl-swpc-z2like-programming`) and the lab launchers now pass it. A Gateway rendered by the Z2 installer on a host without the Bootstrap admission socket answers writes with 503.
* **Migration:** first start of the new Bootstrap migrates `control-token` → controller generation 1 (same secret) and removes the file; the Manager migrates `bootstrap-credentials.json` v1 → v2 generation 1. The existing SWPC↔Z2 relationship continues without re-enrollment.
* **Rollback (Bootstrap to P2A-1):** before starting the old service, root recreates the legacy file from the current record (`controller/controller.json` field `credential` → `/var/lib/plasma-bootstrap/control-token`, mode 0600). **Manager rollback:** schema-2 files are rejected by the old Manager; rewrite as schema 1 (drop `generation`, `controller_id`). If a takeover happened after migration, the rollback credential is the new controller's. Runtime rollback restores the unbound Gateway.

## 7. Tests and evidence (Host-only)

| Suite | Result |
| --- | --- |
| P2A-0 reference model (`test_lom_p2a0_enrollment_spec.py`) | 35 PASS |
| Same 35 cases against the real engine (`test_lom_p2a2_reference_equivalence.py`, real files) | 35 PASS |
| Controller engine (`test_lom_p2a2_controller.py`): RFC 7748, mirror identity, button binding/contention/busy/disabled/malformed, long-press/debounce (incl. release-edge bug found and fixed), stale window after a concurrent lockout (bug found and fixed), simulated sysfs GPIO, board profile, Engineering Mode policy, CLI root refusal, concurrent claims, fence deferral/blocking, rename crash injection, corrupt/broad records, real safety probe (seals, lease socket, reload fence from another process) | 44 PASS |
| G13 + enrollment end to end (`test_lom_p2a2_gateway_g13.py`): real Bootstrap HTTP + admission socket + Gateway mixin + Manager signer | 11 PASS |
| Python 3.10.12 (stock-PYNQ version) compile + engine smoke | PASS locally; CI `bootstrap-scripts` matrix runs the engine suites on 3.10 and 3.12 |
| Migrated regressions (Bootstrap, owner authorization, Manager, request auth, programming CLI, z2like contract, Web contract tests) | see the PR |

Hosted CI run IDs are recorded in the PR. Host-only PASS is not hardware PASS.

## 8. LOC (vs `origin/main` c689549e7)

See the PR description for the final Production / Test / Documentation Added / Deleted / Net table.

## 9. Open items and Gate 2 readiness

* NOT_RUN: everything on hardware — GPIO wiring and live line ownership, long press on the real button, real enrollment, SD boot consumption on the Z2 (the factory installer now renders and enables `plasma-enroll-boot.service`, oneshot `Before=plasma-bootstrap.service`, `ConditionPathIsMountPoint=/boot`; the PYNQ boot-partition mount point is unverified), admission socket under the real systemd hardening, synchronized deployment, rollback drill.
* Owner decisions: active-MITM residual of the button entry (§2.1); disposition of the Bearer-principal Gateway (§5).
* Gate 2 readiness: Draft PR with green Host-only CI; merge needs Gate 2; deployment and hardware steps need separate approval.

## 10. Z2 GPIO verification steps (for a separately approved hardware session)

1. Read-only, no wiring: `gpiodetect`; `gpioinfo zynq_gpio` (or the chip whose label is `zynq_gpio`) — line 12 must be unused; `cat /sys/kernel/debug/gpio`; `grep -r gpio /proc/device-tree` for any user of gpio0 line 12; `devmem 0xF8000730` (MIO_PIN_12) — expect GPIO function, 3.3 V LVCMOS, pull-up; read the line idle level = 1.
2. Power off. Wire a normally-open momentary button between J7 pin 6 and J7 pin 2 (or 3). No series parts needed (10 kΩ on-board pull-up); never configure MIO12 as an output.
3. Power on; confirm idle level 1 and pressed level 0 with a read-only `gpioget`; confirm a press does not reset the board.
4. Copy the board profile to `/etc/plasma/ppu-enrollment-button.json` (root, 0644) with `enabled: true`; restart the Bootstrap service (approved maintenance window).
5. From the Control Station: **Enroll with PPU Button** → hold the button 3 s → **Complete Enrollment**; record controller generation, mode and the Bootstrap log events (`ENROLLMENT_BUTTON_REQUESTED`, `ENROLLMENT_ARMED:ps-gpio-button`, `CONTROLLER_COMMITTED`).
6. Negative checks: short press (< 3 s) arms nothing; press with no request arms nothing; a second station requesting in the window gives `ENROLLMENT_CONTENDED`; SRST1 reset during idle does not arm.
