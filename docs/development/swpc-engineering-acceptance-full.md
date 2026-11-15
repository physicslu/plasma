# SWPC Engineering Acceptance — independent Deploy, HIL and optional Full E2E

**Gate 1 Draft, Host-only implementation; hardware HIL NOT_RUN, SWPC deploy NOT_RUN.**

This coordinator is an engineering-only **composition**, not another installer,
programming engine, HIL backend or automatically scheduled CI job. Do not
promote it to production/factory control. It runs on SWPC and calls the
reviewed `plasmactl` entrypoints sequentially.

## Independent commands

| Command | Deploy SWPC | Real DUT Program | Purpose |
|---|---|---|---|
| `plasmactl deploy local-control-station` | Yes | No | Release activation, Manager/Console health |
| `plasmactl verify local-control-station` | No | No | Existing runtime qualification |
| `plasmactl hil programming --profile bluepill-ab ... --execute` | No | Yes | Single-Site Manager Batch → USB CDC |
| `plasmactl acceptance full --profile bluepill-ab ... --execute` | Yes | Yes | Deploy → Verify → HIL |

The **Deploy preflight** in Draft PR #1435 and the **Manager Batch + Blue Pill
CDC HIL** in Draft PR #1436 are prerequisites for Full. This PR does not
reimplement those components. Merge #1435 and #1436 through their own Gate 2,
integrate both into `main`, and only then qualify this coordinator. Neither
Deploy nor HIL alone is allowed to start its sibling implicitly.

## Reviewed source and physical authorization

The default is a read-only **PLAN_ONLY** report and validation of the exact
v0.1/v0.2 firmware fixture bytes. No Manager request, SWPC deployment or DUT
I/O occurs. For an explicitly owner-authorized SWPC engineering run, require
both `--execute` and `--expected-source-sha` matching the current clean,
committed checkout.

```bash
# In a reviewed, clean SWPC engineering worktree.
./scripts/plasmactl acceptance full --profile bluepill-ab \
  --image-v01 /trusted/v01.bin --image-v02 /trusted/v02.bin \
  --ppu-alias z2 --site 2 \
  --port /dev/serial/by-id/<verified-bluepill-cdc>

# Gate-approved execution only:
./scripts/plasmactl acceptance full --profile bluepill-ab \
  --image-v01 /trusted/v01.bin --image-v02 /trusted/v02.bin \
  --ppu-alias z2 --site 2 \
  --port /dev/serial/by-id/<verified-bluepill-cdc> \
  --expected-source-sha <40-hex-reviewed-HEAD> --execute
```

This is a CLI syntax reference, **not** a command to execute before the
dependencies and physical Site/USB owner have been verified.

The Full composition performs:

1. Source SHA and clean checkout admission.
2. HIL fixture preflight (without `--execute`).
3. Canonical SWPC `deploy local-control-station`; its own transaction/PPU
   safety gate and rollback logic remain responsible for activation.
4. `plasmactl status` exact SHA match, then `plasmactl verify`.
5. One separately authorized HIL Smoke sequence, v0.1 → v0.2 → v0.1,
   using the canonical Manager Batch path and real USB CDC ID/Heartbeat.

Both subtools independently enforce their authorization and safe-state gates.
`Full` is not proof of atomic Manager admission quiescence or exclusive
hardware ownership. Its Preview and Deploy checks can be invalidated by a
concurrent operator. Do not run unattended on a shared PPU without an
exclusive Owner/maintenance admission mechanism.

On a stage failure, Full **stops** and records private JSON evidence under
`~/plasma-engineering-acceptance`. It does not automatically retry or
re-submit the HIL Job, reset Z2, redeploy the previous release or repeat a
failed deployment. Failed HIL may leave a Manager Start/Batch with unresolved
outcome: read its separate HIL evidence, reconcile by exact Start/Batch ID
first, and never assume a missing HTTP reply means no hardware action.

A Full PASS is **CLI-driven** Manager → Z2 PS/PL → real DUT → USB CDC
integration; it does not itself automate Browser E/P Mode clicks, external
analog SAFE_OFF, 8-Site simultaneous scheduling or production qualification.
Those require separately scoped evidence.
