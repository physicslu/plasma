# PLASMA Issue #981 — Dedicated SWPC Codex Worker provisioning

**Status: Gate 1 A approved for host provisioning design, PR/testing. Applying this runbook to SWPC is NOT evidenced by creating a PR. Requires SWPC administrator access and GitHub repository runner registration.**

This runbook sets up a **separate** `SWPC-plasma-codex` worker for the merged, strictly read-only Issue #981 pilot. It never substitutes the existing `SWPC-plasma-ci` runner.

## Observed baseline (GitHub Run #38936163993)

The actual SWPC read-only preflight confirmed:

- `SWPC-plasma-ci` observer and `tmux`: PASS;
- `plasma-codex` account: ABSENT;
- `plasma-monitor` group and `/run/plasma-codex` socket directory: ABSENT;
- Codex CLI in the **existing CI account's PATH**: NOT FOUND;
- dedicated `SWPC-plasma-codex` runner / dedicated account authentication: NOT CHECKED;
- hardware: NOT TOUCHED.

`codex` not being in `plasma-ci` PATH does not prove it is absent from `<trusted-operator>`'s existing interactive environment.

## Security/implementation choices

The two approval types remain Gate 1 for scoped work and Gate 2 for PR merge. The A/B/C choices only select Gate 1's dispatch behavior; they do not grant open-ended execution. The initial pilot uses **only the approved owner-authored exact Issue #981 comment**, fixed read-only prompt, reviewed `main` checkout, `--sandbox read-only --ask-for-approval never`, no shell code from issue body, `contents: read` and no persistent checkout credentials.

**Repository is public.** GitHub cautions that self-hosted runners on public repositories can be exposed to untrusted PR code. Restrict job routing to a reviewed, owner-only, `main`-anchored event and isolate the dedicated OS identity; don't give it `docker`, `sudo`, Z2 credentials, `/dev/mem`, `/dev/uio*`, USB-Hub power or LA permissions. GitHub labels alone are not a security boundary. Audit repository Workflow paths whenever expanding dispatch. This is a POC isolation design, not proof of complete network isolation.

## One-time local administrator bootstrap (after this PR merges)

**Do not copy/paste a remote installer through `curl | bash`.** Pull reviewed `main` to an authorized local checkout on **SWPC**, verify its SHA and no unrelated changes, set `PLASMA_REPO` to that checkout path, then run this dedicated script using your existing privileged SWPC administrative channel, not the `plasma-ci` account:

```sh
cd "${PLASMA_REPO:?set trusted checkout path}"
git status -sb
git fetch origin main
# Confirm that you are running reviewed code and haven't overwritten existing work.
bash scripts/plasma-codex-host-provision.sh --check
sudo bash scripts/plasma-codex-host-provision.sh --apply
bash scripts/plasma-codex-host-provision.sh --check
```

The `--apply` entrypoint verifies `hostname=SWPC`, root privileges, *not* executing in GitHub Actions, account identities and directory conflicts before changes. It idempotently:

- creates locked-down `plasma-codex` system user, private HOME and `actions-runner` directory;
- creates `plasma-monitor`, adds trusted `<trusted-operator>` and `plasma-codex` only to that monitor group (new SSH login needed for group membership);
- writes `/etc/tmpfiles.d/plasma-codex.conf` **only if absent or byte-compatible**; creates `/run/plasma-codex` owner `plasma-codex:plasma-monitor`, mode `2770`, persistent across reboots via systemd-tmpfiles;
- explicitly refuses any reused worker account with unexpected home/shell, root uid, privileged groups, or conflicting socket paths.

It **does not** install a runner, install Codex, change sudoers/firewall, grant hardware permissions, restart existing services, modify `plasma-ci`, use stored credentials or create an arbitrary shell endpoint.

If the root channel is unavailable, record **HOST_PROVISIONING_BLOCKED** and stop. Do not grant CI sudo. Avoid invoking `--apply` from an unreviewed PR worktree.

## Install Codex under the *new* worker identity

Use an official supported Codex CLI installation method suited to SWPC; verify the installed CLI via the dedicated worker's login environment. Do not silently copy `<trusted-operator>`'s `~/.codex` authentication or session files. Supply an explicit service-suitable Codex authentication path owned by `plasma-codex` and protected with `0700/0600` permissions, outside the repo, never in GitHub PR/Issue/CI logs.

Commands that only verify tool availability (without starting an AI session) under that account:

```sh
codex --version
codex exec --help
tmux -V
python3 $PLASMA_REPO/scripts/plasma-codex-worker-readiness.py --json
```

The checker reports **prerequisites** only. Codex CLI version/help success is NOT authentication or API readiness. Never log `env`, `~/.codex`, personal access tokens, or runner `.credentials`.

## Dedicated GitHub Actions Runner enrollment

1. As the repository owner, open `https://github.com/physicslu/plasma/settings/actions/runners/new` and use the **official GitHub Actions x64 Linux runner instructions**, including the exact version-pinned runner download + official SHA256 verification. Do **not** install into the existing runner directory.
2. Extract the verified runner under `/home/plasma-codex/actions-runner`, owned by `plasma-codex`, mode `0700`. Do not make it group/world writable or share the other runner's HOME.
3. Register via the official `./config.sh` procedure **as the `plasma-codex` account**:
   - Repository URL: `https://github.com/physicslu/plasma`
   - Runner name: `SWPC-plasma-codex`
   - Custom label: `plasma-codex`, retaining built-in `self-hosted,linux,x64` labels
   - Work folder: `_work`
   - Registration token: obtain freshly in GitHub; never save in a repo, Issue, PR, text artifact, shell history or CI output. This is a one-time secret with limited lifetime.
4. Use the official `svc.sh install plasma-codex` and `svc.sh start` from the *new runner directory* under an authorized admin channel. Do not install or restart the existing `plasma-ci` service. Check the actual systemd service identity and state; do not assume `svc.sh` created correct service ownership merely because it returned 0.
5. GitHub Repository Settings → Actions → Runners must show **SWPC-plasma-codex Online / Idle**, with exactly the expected repository access. Confirm runner labels and no other workflows dispatch the new label.

GitHub warns about self-hosted runners in public repositories: owner-only dispatch and fail-closed checks are mandatory. Never accept arbitrary PR source code, externally controlled shell, unsanitized Issue content, or `pull_request_target` on this runner. The GitHub service connection uses outbound HTTPS and does not require exposing a new inbound SWPC port.

## Live tmux operation

The pilot's tmux socket is `/run/plasma-codex/pilot-<RUN_ID>.sock` and the tmux session is `plasma-codex-<RUN_ID>`. From the trusted operator's new SSH session:

```sh
tmux -S /run/plasma-codex/pilot-<RUN_ID>.sock attach-session -r -t plasma-codex-<RUN_ID>
```

Use `Ctrl+B`, `D` to detach. This is read-only by client convention, **not a kernel-enforced untrusted-user read-only authorization**; only the trusted operator belongs to `plasma-monitor`. To enforce hard read-only for less-trusted observers, provide a separate ACL-controlled log viewer instead of direct tmux socket access. The socket exists only while the task runs.

## Post-enrollment validation

Run `python3 scripts/plasma-codex-worker-readiness.py --json` under `plasma-codex` and verify prerequisites; it does not prove online/authentication/sandbox/network isolation. Then, using the owner-authorized Issue #981 trigger on merged `main`, dispatch the fixed read-only pilot:

```text
/plasma-codex pilot 981
```

Verify real GitHub `authorize` PASS, `pilot` scheduled on the **separate** `SWPC-plasma-codex` runner, Codex produced a genuine exit code, exact tmux Session was observable, sanitized result artifacts and SHA-256 validated, and no hardware operations ran. The workflow may fail on Codex auth or sandbox constraints; record FAIL/BLOCKED rather than changing to dangerous full access.

**Pass criteria:** end-to-end GitHub → SWPC separate Runner → Codex → tmux → GitHub report works without interactive approvals and without granting host hardware access. Keep the original CLI session and older CI jobs running. Do not proceed to workspace-write or HIL automation until this first pilot has real PASS evidence.

## Recovery / rollback

If bootstrap prerequisites fail, stop, leave the original `plasma-ci` runner untouched, and report concrete blockers. If the newly registered runner must be revoked, stop its dedicated service, remove only `SWPC-plasma-codex` in GitHub administration, revoke its isolated authentication and remove only the dedicated runner service/directory after inventory. Do not automatically delete accounts, monitor groups, unrelated paths, evidence or existing services; cleanup is a separate inspected operation.

## References

- [GitHub: Adding self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)
- [GitHub: Installing a runner service](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application)
- [Codex CLI command reference](https://learn.chatgpt.com/docs/cli/reference)
