# Persistent Integration Runner Enrollment

## Purpose

This runbook turns a prepared Linux x64 machine into the dedicated Plasma L4 persistent integration runner expected by:

```text
.github/workflows/persistent-integration-host.yml
```

It is an operational enrollment procedure, not proof that a runner is currently enrolled. A repository document, runner configuration screen, or workflow definition is not L4 execution evidence.

The architecture and threat model remain defined by:

```text
docs/architecture/persistent-integration-host-qualification.md
```

## Trust boundary

The intended runner process uses a non-root host account with access to a **rootful Docker daemon**. That account is host-privileged in practice and the machine must not be treated as a sandbox.

The persistent runner is a qualification appliance for reviewed `main` code. It is not a general-purpose worker for arbitrary pull requests.

Do not place any of the following on the runner unless a future architecture explicitly requires and protects them:

- production deployment credentials;
- PYNQ-Z2 credentials;
- unrelated SSH keys;
- cloud administration credentials;
- long-lived GitHub registration tokens;
- secrets for unrelated services.

## Qualification state model

Plasma uses these L4 infrastructure states:

```text
UNPROVISIONED
    |
    | host prerequisites prepared and readiness evidence PASS
    v
HOST_READY
    |
    | GitHub Actions runner enrolled and restricted
    v
RUNNER_ENROLLED
    |
    | main-only persistent workflow completes and canonical summary PASS
    v
L4_PASS
    |
    +--> STALE
    |
    +--> REVOKED
```

Definitions:

- `UNPROVISIONED`: host has not produced current readiness evidence.
- `HOST_READY`: `persistent-integration-host-readiness.py` passed on the intended runner identity.
- `RUNNER_ENROLLED`: the GitHub runner is registered/restricted and the in-workflow preflight can execute.
- `L4_PASS`: the canonical persistent qualification summary passed for one exact `main` SHA and one bound host/run identity.
- `STALE`: previously valid evidence no longer represents current `main` or the bound host fingerprint changed.
- `REVOKED`: an administrator intentionally withdraws trust, regardless of previous PASS evidence.

There is no fixed time-to-live encoded today. Exact-SHA drift and material host-fingerprint drift are mandatory staleness triggers. A future governance policy may add a time-based expiry without weakening those triggers.

## Phase 1 — Prepare the host

Use a dedicated non-root account for the Actions runner. Before enrollment, prepare these prerequisites outside the repository automation:

- Linux x64;
- Python 3;
- Git;
- Node.js and npm;
- `ip` from iproute2;
- GNU `stat`;
- rootful Docker accessible by the intended runner account without `sudo`;
- ARMv7/QEMU/binfmt execution already provisioned;
- the pinned Plasma ARMv7 image already present locally;
- persistent state root owned by the intended runner uid/gid and not group/world writable.

The default persistent state root is:

```text
$HOME/.local/state/plasma-ci
```

Provision it before running readiness, for example using an administrator-approved host procedure that results in mode `0700` and ownership by the intended runner identity.

Do not make the readiness checker responsible for host provisioning.

## Phase 2 — Run non-provisioning readiness

From a trusted checkout of Plasma, under the exact host account intended to run GitHub Actions:

```bash
python3 scripts/persistent-integration-host-readiness.py \
  --persistent-root "$HOME/.local/state/plasma-ci" \
  --report ./plasma-persistent-host-readiness.json
```

The checker is deliberately fail-closed. It does not:

- use `sudo`;
- install packages;
- create the persistent state root;
- change ownership or permissions;
- configure firewall or networking;
- install or mutate binfmt/QEMU;
- pull the ARMv7 image;
- enroll a GitHub runner;
- restart services;
- access PYNQ-Z2 hardware.

It may create an ephemeral Docker probe container and writes only the requested evidence report. The ARM image uses `--pull=never`, no network, no Linux capabilities, and no-new-privileges.

A PASS report must contain:

```text
status = PASS
qualification_state = HOST_READY
z2_hardware_claim = NONE
```

Do not continue enrollment after a FAIL by bypassing the failed prerequisite.

## Phase 3 — Obtain runner package and one-time registration token

Use GitHub repository administration for `physicslu/plasma` to start the official **New self-hosted runner** flow.

Security requirements:

1. Download the runner only from the official GitHub Actions runner release source shown by GitHub.
2. Verify the published package checksum before extracting it.
3. Treat the registration token as ephemeral secret material.
4. Never paste a registration token into a repository file, issue, PR, shell script committed to Git, CI variable checked into source, or documentation.
5. Do not reuse an expired or previously exposed registration token.

The runner release/version changes over time, so this repository does not hard-code a downloadable runner version or registration token.

## Phase 4 — Configure runner identity and labels

Configure the runner for repository `physicslu/plasma` using the one-time registration token and the intended non-root account.

Required label contract:

```text
self-hosted
linux
x64
plasma-integration
```

Use an unambiguous runner name that identifies the physical/virtual qualification host without embedding credentials or personal secrets.

The runner must not be configured as an arbitrary organization-wide worker unless an administrator-side runner-group restriction gives an equivalent or stronger isolation boundary.

## Phase 5 — Apply administrator-side restrictions

Repository YAML cannot prove GitHub administrator configuration. Before trusting the runner, verify in GitHub administration that:

- the runner is available only to the intended Plasma repository or an equivalently restricted runner group;
- unrelated repositories cannot schedule work onto it;
- the intended long-lived runner is not used as an arbitrary PR execution worker;
- no secret set exposed to this runner contains production/Z2/unrelated credentials;
- any workflow restriction feature available to the account is narrowed to the intended trusted qualification boundary.

The repository workflow itself remains `workflow_dispatch` + `main` only. These repository checks are defense-in-depth, not a substitute for administrator-side isolation.

## Phase 6 — Install and start the runner service

Use the official GitHub runner service procedure for the host operating system. Run the service as the same non-root identity that produced `HOST_READY` evidence.

After service installation, verify:

- service is running;
- GitHub shows the runner online/idle;
- required labels are present;
- service account matches the readiness uid/gid;
- Docker remains rootful and accessible without `sudo`;
- the persistent root remains owned by that identity and is not group/world writable.

Installing the service is an infrastructure action. It is intentionally not performed by repository scripts.

## Phase 7 — First main-only qualification

From GitHub Actions, manually dispatch:

```text
Persistent integration host acceptance
```

Select `main`. Do not dispatch a feature branch.

A successful run must produce an artifact named:

```text
plasma-persistent-integration-<exact-main-sha>
```

The expected evidence set is:

```text
plasma-persistent-preflight.json
plasma-persistent-environment-fingerprint.json
plasma-static-ipv4-persistent-repeatability.json
plasma-static-ipv4-persistent-repeatability-run1.json
plasma-static-ipv4-persistent-repeatability-run2.json
plasma-persistent-l4-qualification.json
```

The canonical qualification summary is the final machine-readable L4 decision. It must report:

```text
status = PASS
qualification_state = L4_PASS
qualified_sha = <the dispatched main SHA>
z2_hardware_claim = NONE
```

The summary binds the PASS to the GitHub run, runner identity, host/kernel/OS, Docker boundary, pinned ARMv7 image, persistent filesystem, route signature, exact SHA, and SHA-256 digests of its source evidence. The Actions job-start log bound to the same run ID is the runner-version evidence source.

## Phase 8 — Determine staleness

Treat an earlier `L4_PASS` as `STALE` when any mandatory binding is no longer current, including:

- repository `main` moved beyond `qualified_sha` and current-main qualification is required;
- runner host identity changed;
- OS/kernel changed materially;
- Docker server/root boundary changed;
- ARMv7/QEMU boundary changed;
- persistent filesystem/root contract changed;
- default-route fingerprint changed in a way requiring requalification;
- the runner was rebuilt/reinstalled such that the previous run no longer represents the appliance.

Staleness does not mean the old evidence is false. It means it is historical evidence and must not be presented as qualification of the current state.

Re-run readiness when host prerequisites changed. Re-run the persistent workflow after any new trusted `main` revision that requires current L4 evidence.

## Phase 9 — Runner upgrade policy

GitHub Actions runner versions have an external service lifecycle. An enrolled runner must be maintained before GitHub rejects an obsolete version.

For an upgrade:

1. stop scheduling new qualification work;
2. use the official GitHub runner upgrade path;
3. verify package provenance/checksum when a package is manually replaced;
4. restart the runner service;
5. verify labels/repository restriction remain correct;
6. re-run host readiness if host-side prerequisites changed;
7. run a fresh main-only L4 qualification;
8. treat the previous L4 PASS as historical/STALE for the upgraded appliance.

Do not disable version enforcement or pin an obsolete runner as a workaround.

## Phase 10 — Revoke or remove the runner

When the host is retired, compromised, repurposed, or no longer trusted:

1. stop the runner service;
2. remove/de-register it through GitHub administration using the official removal flow;
3. revoke or rotate any credentials that may have been exposed to the host;
4. remove repository/runner-group access;
5. classify the runner state as `REVOKED`;
6. retain prior evidence only as historical audit material according to retention policy;
7. do not reuse old registration tokens.

If compromise is suspected, administrative revocation overrides any prior `L4_PASS` immediately.

## Recovery after host loss

A replacement host starts at `UNPROVISIONED`. Do not copy an old `L4_PASS` designation to a replacement machine merely because the same runner name or persistent-state directory is reused.

The replacement must independently complete:

```text
HOST_READY -> RUNNER_ENROLLED -> L4_PASS
```

## Evidence and hardware boundary

L4 evidence proves a particular persistent Linux integration host and exact reviewed Plasma revision. It does **not** prove:

- PYNQ-Z2 runtime behavior;
- native Z2 networking;
- Ethernet MAC/PHY/cable/switch behavior;
- PS-to-PL communication;
- FPGA Site I/O;
- target power control;
- real IC programming;
- eight-Site concurrent programming.

Those remain L5/L6 work.
