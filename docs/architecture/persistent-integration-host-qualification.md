# Persistent Integration Host Qualification

## Status

This document defines the current L4 persistent integration-host qualification boundary for Plasma.

The current workflow is:

```text
.github/workflows/persistent-integration-host.yml
```

It is a **main-only, manually dispatched, post-merge qualification path**. It is not a required PR gate and it is not PYNQ-Z2/HIL evidence.

## Security premise

A persistent self-hosted runner is materially different from an ephemeral GitHub-hosted runner.

The Plasma L4 runner is expected to use a non-root host account, but that does **not** make the host a sandbox. The qualification requires access to a rootful Docker daemon so that root-owned filesystem evidence can be produced and verified with real ownership parity. On a normal Linux Docker installation, a non-root account that can control the rootful Docker daemon has host-privileged capability in practice.

Therefore the governing security rule is:

> Persistent integration infrastructure may execute only reviewed, trusted main-branch code unless the runner itself is disposable and isolated.

The persistent runner must be treated as a dedicated qualification appliance, not as a general-purpose PR execution worker.

Because GitHub Action code also executes inside this host-privileged boundary, actions used by the persistent self-hosted job must be pinned to an **immutable commit SHA**, not only to a movable major-version tag.

## Evidence ladder

The current validation ladder is:

```text
L0  Static / contract validation
L1  Unit / regression validation
L2  Packaged ARMv7 userspace acceptance
L3  Linux integration acceptance
L4  Persistent integration-host qualification
L5  future PYNQ-Z2 HIL qualification
L6  future real-device / multi-Site qualification
```

A successful L4 execution adds evidence about a retained host workspace, installed Docker/QEMU boundary, filesystem history, ownership residue, and host environment. It does not upgrade any claim to L5 or L6.

## Main-only dispatch contract

The workflow keeps `workflow_dispatch`, but the canonical repository workflow is intentionally constrained to `refs/heads/main`.

The defense is layered:

1. A GitHub-hosted `main-dispatch-guard` job rejects a dispatch whose event, repository, ref, or SHA identity does not match the expected main-only contract.
2. The self-hosted job has an equivalent job-level `if` condition, so a rejected non-main dispatch is not scheduled onto the persistent runner.
3. Before checkout, the self-hosted job rechecks the trusted event identity and non-root runner identity.
4. `actions/checkout` is pinned to an immutable commit SHA, checks out the exact workflow event `${{ github.sha }}` rather than an arbitrary branch name, and persisted Git credentials are disabled. The evidence-upload action is likewise commit-SHA pinned.
5. `scripts/persistent-integration-host-preflight.py` fails unless the checked-out commit exactly equals `GITHUB_SHA` and the event remains a main-branch `workflow_dispatch` for `physicslu/plasma`.

These repository checks are **defense-in-depth**, not a complete protection against a write-capable attacker who can modify the workflow definition itself on another repository branch and then cause that modified workflow to execute.

The infrastructure-side enrollment policy must therefore also constrain the dedicated runner group to the Plasma repository and, where GitHub runner-group policy allows it, to the selected persistent qualification workflow/default-branch execution boundary. Repository code cannot prove that administrator-side runner policy is configured correctly.

## Runner enrollment preconditions

Before a host is labeled:

```text
self-hosted
linux
x64
plasma-integration
```

all of the following should be true:

- the machine is dedicated to Plasma integration qualification or has an equivalent isolation boundary;
- the Actions runner process runs as a non-root host account;
- Docker is rootful and usable by the runner account without `sudo`;
- administrators understand that rootful Docker access makes the runner account host-privileged in practice;
- ARMv7/QEMU execution is provisioned before the workflow runs;
- the workflow is not allowed to install or mutate host binfmt configuration as part of qualification;
- Python 3, Node.js, npm, Git, `ip`, GNU `stat`, and Docker are installed;
- no production credentials, deployment keys, Z2 access credentials, or unrelated service secrets are exposed to the runner;
- the persistent state root is outside both the GitHub checkout and `RUNNER_TEMP`;
- the persistent state root is a real directory, not a symlink, is owned by the runner uid/gid, and is not group/world writable;
- repository / runner-group administration limits the runner to the intended trusted workflow boundary.

The default persistent state root is:

```text
$HOME/.local/state/plasma-ci
```

It may be overridden with `PLASMA_PERSISTENT_CI_ROOT`, subject to the same preflight rules.

## Fail-closed preflight

`scripts/persistent-integration-host-preflight.py` runs before repository setup or tests on the persistent host.

It verifies and records:

- Linux x64 host architecture;
- non-root host uid/gid;
- exact `workflow_dispatch`, repository, `refs/heads/main`, `GITHUB_SHA`, and checked-out SHA identity;
- required host tools;
- persistent-root path, ownership, mode, filesystem, and separation from checkout / runner temp;
- rootful Docker server/security state;
- explicit recognition that Docker access is host-privileged and the runner is not a sandbox;
- already-provisioned ARMv7 execution through the pinned ARMv7 image with no network, no capabilities, and no-new-privileges;
- host default-route evidence and a normalized route signature.

Rootless Docker fails the preflight. Rootless container uid 0 does not provide the real host `root:root` ownership parity required by the Static IPv4 private-evidence contract.

The preflight does not use `sudo`, add Linux capabilities, install QEMU/binfmt, deploy software, restart services, access a Z2, or modify production networking.

## Qualification execution

After preflight passes, the workflow:

1. runs canonical repository setup and source/configuration validation;
2. builds the PPU runtime from the exact dispatched main SHA;
3. clean-extracts and validates the immutable `linux-armv7l` PPU release;
4. captures the environment and packaged-artifact fingerprint;
5. executes Static IPv4 same-workdir repeatability and privilege/ownership parity using the persistent state root;
6. uploads exact-SHA acceptance evidence.

The retained artifacts include:

```text
plasma-persistent-preflight.json
plasma-persistent-environment-fingerprint.json
plasma-static-ipv4-persistent-repeatability.json
plasma-static-ipv4-persistent-repeatability-run1.json
plasma-static-ipv4-persistent-repeatability-run2.json
```

The artifact name also contains the exact GitHub SHA.

## What L4 currently means

An observed PASS on an enrolled persistent runner would prove that the current reviewed main revision passes the L4 contracts on that particular persistent Linux host and retained workspace.

At the time this document is introduced, the repository path exists but no successful execution on an enrolled `plasma-integration` runner is claimed. A workflow definition is not execution evidence.

The L4 workflow is deliberately **not a required PR gate** today. The repository also cannot claim that administrator-side runner-group restrictions or required status checks are configured merely because repository YAML expects them.

## Why this is not a pre-merge PR runner

Running arbitrary pull-request code on a long-lived self-hosted host with rootful Docker would create a larger security boundary than the software evidence justifies.

Do not add `pull_request` or `pull_request_target` as a shortcut for executing PR code on this persistent runner. `pull_request_target` does not make untrusted PR code safe if the workflow later checks out or executes that PR's content.

A future pre-merge L4 gate requires a different execution model, preferably an **ephemeral/disposable runner** whose host, filesystem, credentials, and Docker boundary can be destroyed after one qualification. Another acceptable design would need equivalent isolation and a demonstrable policy that unreviewed PR code cannot gain durable host trust.

Only after that infrastructure exists should Plasma consider making persistent-class acceptance a required pre-merge status check.

## Hardware boundary

A persistent Linux L4 PASS does **not** prove:

- PYNQ-Z2 Linux runtime behavior;
- the PYNQ-Z2 native network-manager backend;
- physical Ethernet MAC/PHY/carrier/switch behavior;
- DHCP migration or reboot persistence on Z2;
- PS-to-PL communication;
- FPGA Site I/O or timing;
- target power control;
- real IC programming;
- eight-Site concurrent programming.

Those remain L5/L6 qualification work and require separate Gate-1-approved hardware execution when implemented.
