# LOM-P2A-1 synchronized deployment runbook (SWPC Manager/CLI + Z2 Bootstrap)

> **Status: PLAN ONLY — deployment NOT authorized.** Do not touch the SWPC Control Station, the Z2 or any DUT until the owner gives an explicit deployment approval naming this runbook and its pins. Approval of this document is not approval of any later P2A-x implementation.
> Change being deployed: [PPU Bootstrap mutual request authentication](ppu-bootstrap-request-authentication.md) (#1372, merged in `main` `3c2145f3d`). Policy: [ADR-0008](../adr/0008-local-owner-mode.md). Design context: [B1–B5 proposed design](../development/opf-local-owner-mode-b1b5-design-20261109.md).
> Contracts: [AGENTS.md](../../AGENTS.md), [Embedded](../development/plasma-embedded.md) (SSH/sudo, seals, recovery), [Manager](../development/plasma-manager.md), [Bootstrap factory refresh](ppu-bootstrap-factory-and-hil.md#single-z2-rd-refresh-current-development-route).

## 1. Pins (verify each before the window; any mismatch = STOP)

| Item | Pinned value | How verified |
| --- | --- | --- |
| Source | `main` `3c2145f3d155…` (post-merge CI 10/10 success) | `git rev-parse` in a clean worktree |
| Z2 factory Bootstrap bundle | `plasma-ppu-bootstrap-0.1.0-3c2145f3d155.tar.gz`, SHA256 `dfed1a54f0e121c5753841bf3e020dfbfd51cabd5bc6560965ce38fc1a0bfb97`, Actions run `42577713699` artifact `ppu-bootstrap-factory-bundle` (expires 2026-11-23) | `sha256sum -c` against the CI sidecar, on SWPC and again on Z2 |
| SWPC Control Station target | release `3c2145f3d155` built by `scripts/plasmactl-local-control-station deploy` from a clean worktree at `3c2145f3d` | `plasmactl-local-control-station status` |
| SWPC Control Station previous (rollback) | expected `2efb4543f…` (#1369 deploy). **Record the actual `current` symlink target in P1**; that is the rollback pin | P1 |
| Z2 Bootstrap previous (rollback) | reports only `bootstrap.version = "0.1.0"` (no SHA, gap G9). Rollback pin = the **file-level SHA256 inventory + tarball** captured in P5/P6 | P5/P6 |
| Z2 Runtime | `0.2.1-a1b1c6f3b142` — **not changed** by this runbook | `/v1/status` before/after |
| Active Set | expected generation 13 `4d2837d4…` (evidence #1370). Record actual value in P4 | `/v1/assets` |
| Hosts / ports | Z2 `192.168.2.99` (Bootstrap `:18081`, Gateway `:18080`); SWPC Manager `127.0.0.1:18280`; Console/BFF `127.0.0.1:18190`; alias `z2` | P1/P2 |

## 2. Version compatibility matrix

| Z2 Bootstrap ↓ / client → | SWPC Manager ≤ `2efb4543f` (Bearer) | SWPC Manager `3c2145f3d` (P2A-1) | Path 2 CLI work order at `--source-sha` < `3c2145f3d` | Path 2 CLI at ≥ `3c2145f3d` |
| --- | --- | --- | --- | --- |
| **Current Bearer Bootstrap** | Works (today) | Anonymous status works; every authenticated call fails: `GET /v1/auth/challenge` → 404 → "challenge unavailable". **No side effect** | Works | Fails `API_CHALLENGE_REJECTED:404`; no side effect |
| **P2A-1 Bootstrap (`3c2145f3d`)** | Every POST → 401 `unauthorized`; Console shows pairing/authorization failure. **No side effect** | **Works** (target) | Fails `API_HTTP_REJECTED:401`; no side effect | Works |
| Z2 Runtime `a1b1c6f3b` | Unaffected (Runtime does not call Bootstrap HTTP) | Unaffected | Unaffected | Unaffected |
| z2like-demo QEMU / Render profiles | Separate Bootstrap inside the QEMU kit; **out of scope** for this window; CI `qemu-bootstrap-e2e` already PASS on `3c2145f3d` | — | — | — |

Every mixed state fails closed with 401/404 **before** any write, but it is non-functional. Therefore both sides change in **one window**, and rollback restores **both** sides (§6).

Persisted credentials are compatible: the Manager `bootstrap-credentials.json` schema is unchanged and the Z2 `control-token` is **not rotated**, so the existing pairing must keep working without re-entry.

## 3. Stop conditions (any one → stop, no further write, report)

- Any active or queued Site Job; any Bootstrap deployment `queued`/`running`/`activating`/`recovery_required`; any Manager programming run `OUTCOME_UNKNOWN` without reconciliation; any `site<N>.sealed` marker.
- Pin mismatch (§1), sidecar mismatch, or a P5 file diff the owner has not explicitly accepted.
- `plasma-bootstrap.service` not `active` after restart, or `/v1/status` not `bootstrap_ready`.
- Any acceptance item in §5 FAIL.
- Never: rotate the Z2 token, delete/restore `/var/lib/plasma-bootstrap` journals over newer state, clear seals, re-send an uncertain write, or print/copy credential contents into evidence.

## 4. Procedure

Conventions: run on SWPC as the Control Station user. `Z2` commands run over the owner-approved SSH/sudo channel defined in the Embedded contract (credential store outside the repo; sudo password via stdin; never echoed). `EV=<evidence-root>/lom-p2a1-deploy-<UTC>` (mode `0700`); store secret-bearing backups **outside** `EV`.

```bash
Z2=192.168.2.99; MGR=http://127.0.0.1:18280; BFF=http://127.0.0.1:18190
STATE=~/.local/state/plasma/local-control-station
```

### Pre-window (read-only; may be run on the approval day)

- **P1 SWPC state.** `scripts/plasmactl-local-control-station status`; `readlink -f ~/.local/share/plasma/local-control-station/current` → record as SWPC rollback pin; `systemctl --user is-active plasma-local-manager.service plasma-control-station.service`.
- **P2 Manager view.** `curl -fsS $MGR/api/registry/z2/bootstrap | jq '{pairing, state:.bootstrap.bootstrap.state, runtime:.bootstrap.runtime.release_id, deployment:.bootstrap.deployment.state}'` → expect `paired:true`, `device_match:true`, `bootstrap_ready`, Runtime `0.2.1-a1b1c6f3b142`, deployment state terminal.
- **P3 Manager run journal.** `jq '[.. | objects | select(.outcome? == "OUTCOME_UNKNOWN" and (.acknowledged? != true))] | length' $STATE/bundle-programming-runs.json` → `0`; no non-terminal run.
- **P4 Z2 read-only.** `curl -fsS http://$Z2:18081/v1/status` (record `identity.device_id`, `deployment`), `curl -fsS http://$Z2:18081/v1/assets` (record Active Set SHA/generation), `curl -fsS http://$Z2:18080/api/status` (no active/queued Job; Site 2 idle). On Z2: `sudo jq '{state,kind,transaction_id}' /var/lib/plasma-bootstrap/deployment.json`; `sudo /usr/bin/python3 /opt/plasma/bootstrap/ppu_site_recovery.py diagnose 2` (and `1`) → no seal; `systemctl is-active plasma-bootstrap.service plasma-site-worker.service plasma-server.service`.
- **P5 File inventory and diff (gap G10).** On Z2: `sudo sha256sum /opt/plasma/bootstrap/* > /tmp/bootstrap-before.sha256` (copy to `EV`, hashes only). On SWPC: extract the pinned bundle and `sha256sum plasma-ppu-bootstrap-*/scripts/*`. Produce the list of files that would **change**, be **added** or are **only on the device**. **The Site Worker runs from `/opt/plasma/bootstrap`** (`scripts/ppu_package_units.py` `RUNTIME_DIR`), so `--refresh-only` also replaces Worker/adapter/engine code if those hashes differ. The owner must accept the exact diff list as part of the deployment approval. Expected minimum: `ppu-bootstrap-service.py` (changed), `ppu_bootstrap_request_auth.py` (added), `ppu-bootstrap-installer.py` (changed). If Worker files differ, the approval must also cover a Worker restart (W4) and the Site 2 acceptance (A5) becomes the regression check for them.
- **P6 Backups (private, not in `EV`).**
  - Z2: `sudo du -sh /var/lib/plasma-bootstrap`; `sudo tar -C / -czf /var/backups/plasma-lom-p2a1-<UTC>.tgz opt/plasma/bootstrap var/lib/plasma-bootstrap etc/systemd/system/plasma-bootstrap.service etc/plasma/ppu-package-target.json && sudo sha256sum /var/backups/plasma-lom-p2a1-<UTC>.tgz` (record the hash in `EV`). Also record the token's SHA256 only: `sudo sha256sum /var/lib/plasma-bootstrap/control-token | cut -c1-64`.
  - SWPC: `umask 077; tar -czf ~/plasma-backups/lom-p2a1-<UTC>-swpc.tgz -C ~ .local/state/plasma/local-control-station .config/plasma/local-control-station .config/systemd/user/plasma-local-manager.service .config/systemd/user/plasma-control-station.service` (contains the 0600 credential file; never published).
  - Device identity, Active Set and recovery information are captured by P4 + these archives; nothing is modified.

### Window (single maintenance window, one operator, no concurrent Path 2 work orders)

- **W0 Freeze.** Announce the window; ensure no Path 2 dispatch is queued; `systemctl --user stop plasma-control-station.service` (prevents Console writes; Manager keeps serving reads).
- **W1 Re-gate.** Repeat P2–P4 quickly. Any change since pre-check → STOP.
- **W2 Transfer.** Copy the pinned bundle **and** `.sha256` sidecar to `Z2:/tmp/plasma-lom-p2a1/`; on Z2 `sha256sum -c plasma-ppu-bootstrap-*.tar.gz.sha256 && tar -xzf plasma-ppu-bootstrap-*.tar.gz`.
- **W3 Z2 Bootstrap refresh.** In the extracted directory: `sudo /usr/bin/python3 scripts/ppu-bootstrap-installer.py --source-root "$PWD/scripts" --host 192.168.2.99 --refresh-only` → JSON `result:"PASS"`, `operation:"refresh_only"`, `unit_changed:false`, `control_token_provisioned:false`. Re-confirm Site idle and no deployment in flight, then `sudo systemctl restart plasma-bootstrap.service`; `systemctl is-active plasma-bootstrap.service` → `active`.
- **W4 Worker restart (only if P5 showed Worker-file changes and the owner approved it).** With Site 1/2 idle: `sudo systemctl restart plasma-site-worker.service`; `systemctl is-active` → `active`; `ppu_site_recovery.py diagnose 2` → no seal.
- **W5 Z2 post-refresh checks.** `sudo sha256sum /opt/plasma/bootstrap/*` equals the bundle for every shipped file; token SHA256 unchanged; `curl http://$Z2:18081/v1/status | jq .security.request_authentication` → `"plasma.ppu.bootstrap-request-auth.v1"`, `bootstrap_ready`, Runtime and deployment record unchanged; `curl http://$Z2:18081/v1/auth/challenge` → 200 with the **same** `device_id` as P4.
- **W6 SWPC Manager/Console.** `git worktree add <worktree-root>/plasma-wt-cs-3c2145f3d 3c2145f3d` (clean), then from it `scripts/plasmactl-local-control-station deploy` → `deployment complete: 3c2145f3d155`; `scripts/plasmactl-local-control-station verify` PASS (Console + Manager + Selector). The deploy restarts both user services.

## 5. Acceptance (all must PASS; record observed values)

| ID | Check | PASS criterion |
| --- | --- | --- |
| A1 | Versions | SWPC `status` release `3c2145f3d155`; Z2 shipped-file hashes = bundle; Runtime `0.2.1-a1b1c6f3b142` unchanged |
| A2 | Pairing kept, mutual proof | `curl $MGR/api/registry/z2/bootstrap` → `pairing.paired:true`, `device_match:true`, **`device_authenticated:true`**, `device_id` = P4; no re-pair, token SHA256 unchanged |
| A3 | Signed POST + PPU response proof, no side effect | Using the deployed release venv (credential read in memory from `$STATE/bootstrap-credentials.json`, never printed): `BootstrapHttpClient(...).create_upload(cred, device_id, {"size":0,"sha256":"0"*64})` → `409` with message starting `size must be an integer` (the client raises if the response MAC is missing/invalid); Z2 upload record count unchanged |
| A4 | Device negatives | `curl -X POST http://$Z2:18081/v1/uploads -H 'Authorization: Bearer not-the-token-…' -d '{"size":0,"sha256":"<64 zeros>"}'` → `401`; same without header → `401`; a signed request re-sent with the identical header → `401` (replay); no upload record created |
| A5 | Console Site 2 Flash/Readback (owner in the real Console UI) | Route `z2-site2-stm32f103c8t6`, image Blue Pill CDC v0.1 `8d3ffb02…` 18,768 B → expected `ALREADY_ACTIVE` (MACed status + assets) → `FLASH_CYCLE_SUBMIT` → receipt `PASS`; `readback_sha256 = 8d3ffb02…`, 18,768/18,768 verified, **`safe_off:true`**, **`attempts:1`**; UI receipt, Manager run journal and PPU Job status agree; Site 2 back to idle |
| A6 | *(Owner option)* signed B1/B2/B3 on hardware via Console cache-miss | Only if the owner names a second image (candidate: committed CDC phase-A image `7ce5d3b9…` 18,328 B) and approves the Active Set changes. Same receipt criteria as A5, then optionally restore v0.1 the same way. If skipped: record **signed B1/B2/B3 on hardware = NOT_RUN** (Host-only + CI QEMU cover it) |
| A7 | No residue | Bootstrap deployment terminal; no `OUTCOME_UNKNOWN`; no seal; Active Set = P4 value (or the A6 values if A6 ran) |
| A8 | Claims | Report states: TLS confidentiality **NOT_QUALIFIED**; manual credential entry still required until P2A-2 + P1; Path 2 work orders must use `--source-sha ≥ 3c2145f3d` |

## 6. Coordinated rollback

**Triggers:** W3–W6 failure, any A1–A5 FAIL, or an unexplained state change. Rollback restores **both** sides; never leave a mixed pair.

- **R0 Uncertain writes first.** If a Flash, B1/B2/B3 or deployment was submitted and its outcome is not proven, **do not re-send it**. Record `OUTCOME_UNKNOWN`, reconcile read-only (Manager journal, PPU `/api/status?job=`, Bootstrap `/v1/deployment`, Site diagnose) and acknowledge (`OUTCOME_UNKNOWN_RECONCILED`) only after reconciliation. Code rollback proceeds only when no deployment is in flight and Sites are idle; otherwise stop and escalate.
- **R1 SWPC.** From a clean worktree at the P1 rollback SHA run `scripts/plasmactl-local-control-station deploy` (the retained release directory is reused), then `verify`. If that fails, restore the `current` symlink and units from the P6 SWPC archive and `systemctl --user daemon-reload && systemctl --user restart plasma-local-manager.service plasma-control-station.service`. Do **not** restore `$STATE` unless it is corrupted and the owner approves (it holds the unchanged credential and newer run records).
- **R2 Z2.** `sudo systemctl stop plasma-bootstrap.service`; restore **only** `opt/plasma/bootstrap` from the P6 tarball (`sudo tar -C / -xzf /var/backups/plasma-lom-p2a1-<UTC>.tgz opt/plasma/bootstrap`; first remove the added `ppu_bootstrap_request_auth.py`); verify hashes equal `bootstrap-before.sha256`; `sudo systemctl start plasma-bootstrap.service`; if W4 ran, restart the Worker while idle. **Do not** restore `/var/lib/plasma-bootstrap` over newer transactions.
- **R3 Verify the old pair.** P2 checks pass (`paired`, `device_match`, `bootstrap_ready`); Console read-only view works. A rollback Flash is **not** required; any Flash needs its own approval.
- **R4 Report** both directions with exact SHAs and the rollback reason.

## 7. Evidence (redacted)

`EV/`: P1–P5 outputs (hashes, states, IDs), installer JSON, W5 status JSON, A2–A5 outputs, Console receipt, Manager run record, PPU Job JSON, timeline (UTC). Never include the token, credential file, sudo/SSH secrets or backup tarballs. A follow-up docs-only evidence PR records PASS/FAIL/NOT_RUN per item.

## 8. What this deployment does not change or claim

No enrollment, credential rotation, Registry, Console UX, FPGA image, PL load, Root/privileged code or Runtime change. Transport confidentiality remains NOT_QUALIFIED. "No manual credential" is **not** claimed until P2A-2 and P1 are delivered.
