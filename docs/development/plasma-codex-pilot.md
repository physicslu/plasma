# PLASMA Codex automation: safe SWPC bootstrap (Issue #981)

Status: **Gate 1 A approved; implementation is a staged, read-only PILOT**, not a deployed full-autonomous developer or hardware controller. Keep Gate 2 before merge and independently scope hardware capabilities before HIL.

## Ownership and trust boundary

- ChatGPT creates/reviews a *specific* work order and captures the owner's Gate 1 A/B/C selection. A is dispatch-eligible, B waits for explicit launch, C does not dispatch. Absent selection does **not** dispatch.
- This first bootstrap is deliberately narrow: owner `physicslu` posts the **exact** comment `/plasma-codex pilot 981` on **Issue #981**. No free-form Issue text or untrusted PR content is executed on SWPC. The comment is a separate dispatch event reflecting the previously selected A, not an extra approval gate. The trusted owner/issue/comment/default branch are checked on GitHub-hosted Linux.
- GitHub Actions then schedules a reviewed `main` checkout on dedicated label `[self-hosted, linux, x64, plasma-codex]`. It **will remain queued** until a separate runner is registered on SWPC. Existing `SWPC-plasma-ci` / `plasma-integration` must not be relabeled or repurposed.
- Codex runs only a **hardcoded, public-source read-only prompt**, with the **global** approval flag before the subcommand (`codex --ask-for-approval never exec --sandbox read-only`). The *absence* of approval prompts is not permission to bypass OS controls. The worker cannot commit, push, merge, operate hardware, or act as the existing Gateway/PPU service.
- The bootstrap workflow is picked up from `main` only **after a distinct Gate 2 approval and merge**; adding an Issue or comment while the workflow exists only on a PR branch does not launch anything. Any first-time registration or service setup on SWPC is likewise deployment/configuration and must be in an approved plan. No installer commands are executed automatically by this PR.
- The next iteration is a job registry, per-job signed/owner-authenticated work-order binding, and a writable software-only worker. **This pilot is not that implementation**; do not label it complete general-purpose auto-dispatch.

## SWPC one-time preparation (provision after approval of environment activation)

1. Register a **new** GitHub Actions service runner with name `SWPC-plasma-codex` and sole project-specific label `plasma-codex`. Run it as non-root `plasma-codex`, not `plasma-ci`. Do not share its `~/.codex`, HOME, Docker socket, sudo, GitHub token or FPGA/HIL credentials with other users. Use a separate workspace and bounded disk/resource quotas.
2. Ensure `tmux`, GNU `timeout`, `python3`, Git and supported `codex` are available in its PATH. Authenticate Codex for this *specific account* using an approved service-appropriate method; never commit auth files, relay secrets in GitHub comments or dump credentials in Action logs. Validate the installed CLI supports the supported global-before-subcommand flag ordering (`codex --ask-for-approval never exec --sandbox read-only --json`); passing `--ask-for-approval` after `exec` returns code 2 on Codex CLI 0.162.1.
3. Reserve a `plasma-monitor` group with only the owner and worker permitted, and a volatile `/run/plasma-codex` directory owned by `plasma-codex:plasma-monitor`, mode **2770**, managed by systemd-tmpfiles (recreated on boot). Both `gordon` and `plasma-codex` must have access via that group. **tmux socket group access does not cryptographically enforce read-only**: use `attach-session -r` on a trusted operator account and never share the group with untrusted users. For strictly enforced read-only observers, expose only filtered `tail -f` logs through an independent ACL-controlled viewer.
4. Verify the worker is **not** in `sudo`, `docker`, `adm`, `dialout`, `gpio`, `i2c`, `video` or `plasma-hil`. It must not possess Z2 SSH keys/passwords, `/dev/uio*`/`/dev/mem` access, privileged container membership, USB Hub power privileges, or LA control credentials. Linux isolation must be validated, not inferred from Codex prompt text. For stronger protection, put the dedicated worker in an OS sandbox/container with no host hardware mounts.
5. Ensure the runner is dedicated and no active jobs are displaced. No physical hardware is connected by the pilot. Prevent untrusted PRs, other repositories, and other users from scheduling this privileged label. On a public repository, self-hosted runner isolation and owner-only dispatch are mandatory.

## Actual trigger and observation

Once the bootstrap PR has passed **Gate 2** and required host provisioning is complete, ChatGPT can issue a dispatch comment on #981 *after* the owner's already approved A decision:

```text
/plasma-codex pilot 981
```

The Issue event authorizer checks `repository`, `sender`, `actor`, `comment.user`, `issue.number`, `action`, exact command, absence of PR payload and `refs/heads/main`. A negative test covers spoofing/extra tokens.

While the specific run (for example `<RUN_ID>`) is running, SSH to SWPC and watch:

```sh
tmux -S /run/plasma-codex/pilot-<RUN_ID>.sock attach-session -r -t plasma-codex-<RUN_ID>
```

To detach, press `Ctrl+B`, then `D`. Alternatively, stream the dedicated worker's local `codex.jsonl` through a controlled log reader. The live socket disappears when the Actions job finishes; the GitHub Actions job summary and sanitized output/exit metadata remain. `RUNNER_TEMP` logs may be periodically purged by runner maintenance; configure independent secured retention if long-term logs are required.

## Initial live SWPC pilot (issue #981, software-only)

The first real owner-authorized Issue comment reached the new independent `SWPC-plasma-codex` Runner (GitHub run [#38942529320](https://github.com/physicslu/plasma/actions/runs/38942529320)). GitHub event authorization PASS; checkout PASS; Linux identity, runner name, group and socket directory checks PASS; monitored tmux launched; evidence uploaded. **Codex returned exit code 2, so the pilot was FAIL**. The initial script placed a global CLI flag after `exec`, a known unsupported form. The corrected source keeps `read-only` and `never` unchanged but moves the global flag before the subcommand. This correction is a software change subject to its own Gate 2; a successful post-merge retest is still necessary.

## Acceptance and recovery

- GitHub-hosted contract check and negative authorization tests PASS on the PR; this is *not* SWPC/HIL acceptance.
- Pilot only: a real owner command on #981 queues exactly one job; unknown comment/issue/actor is ignored. This does not establish general work-order dispatch.
- Worker must use the exact `SWPC-plasma-codex` runner and `plasma-codex` Linux user and verify prohibited groups; if missing or unsafe, fail closed.
- Codex `exec` is limited to 900 s independently of the 20-minute Action timeout. Every Codex command approval is non-interactive but may fail due to sandbox, authentication, rate limit or missing CLI.
- Actions waits on a real atomic completion marker and validates SHA-256 of metadata and exit status; failures, signals, lost tmux or timeout are **FAIL/NOT RUN**, never assumed PASS.
- The tmux instance is killed by cleanup on job end. Abnormal host/runner death is an exception requiring an operator to inspect/terminate the session; the inner Codex command still has a 900 s bound.
- No deployment, PR publishing from Codex, `main` mutation, Z2 FPGA manager, MMIO, Hub power control, Logic Analyzer HIL or real DUT operation is authorized.

## Follow-on (not implemented here)

After this read-only pilot is observed on real SWPC: add owner-bound Gate 1 A/B/C task manifests, job deduplication, cancellation and controlled artifact publication, isolated software-write Codex worktrees with GH-mediated PR submission, audit retention/redaction, resource locks, and individually scoped HIL capabilities. Track as subsequent PRs under Issue #981 or scoped follow-up issues, always stopping at Gate 2.
