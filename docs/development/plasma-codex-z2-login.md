# PLASMA Issue #981 — real Z2 SSH/UART login smoke with SWPC live tmux

**Gate 1 implementation in PR; Gate 2 required before merge or dispatch.**
This workflow tests only existing PYNQ-Z2 **SSH and UART login** as the dedicated non-root `plasma-codex` Linux account. It is not an FPGA, JTAG reset, USB hub power, DUT or programming test, and it is not a new HIL Gateway.

## Confirmed baseline and blockers

- Owner-provided SWPC evidence: dedicated Runner process loaded the new `plasma-codex-io` GID; the real post-restart [passive inventory](https://github.com/physicslu/plasma/actions/runs/38952119722) checked Z2 FT2232 USB RW DAC and two generic ttyUSB RW DAC. **This does not prove actual SSH/UART login.**
- Root metadata-only audit reported `plasma-codex`'s own Z2 credential file **ABSENT**. The old operator has an owner-only development credential file; the worker cannot simply read it, and the original operator's private SSH key/password must not appear in GitHub commits, Actions logs, Issue comments or artifacts.
- The owner stated the Z2 development-image account and password are the defaults `xilinx` / `xilinx`. The test **never hardcodes or logs** even a default password. It uses a dedicated local secret file entered securely at the SWPC terminal.
- The target address must be the enrolled board from the operator's already verified lab records, not a guessed LAN IP. SSH host-key pinning must be backed by the operator's trusted known_hosts entry; **do not trust a fresh ssh-keyscan response solely because it connects**.

## One-time worker configuration on trusted SWPC terminal

Before the first hardware dispatch, ensure the operator's existing, known working SSH session can resolve the Z2 target and its **trusted host-key entry**. From the SWPC terminal, the operator can read the private host value without posting it in GitHub or ChatGPT, and look up the existing pinned host key:

```sh
# Under the existing operator account, NOT in GitHub Actions.
# Use the host from the existing owner-approved private lab configuration.
# Do not paste private addresses, passwords or private keys into PR/Issues.
ssh-keygen -F '<trusted-Z2-host-or-IP>' -f "$HOME/.ssh/known_hosts"
```

Use the matched OpenSSH known_hosts entry, **not the preceding comment line** from `ssh-keygen -F`. If there is no previously trusted matching entry, obtain/verify the Z2 host public-key fingerprint through an existing trusted console or already authenticated connection before enrolling. Do not disable StrictHostKeyChecking or silently enable TOFU.

After reviewing and merging this PR (Gate 2), from the **local approved SWPC checkout** run:

```sh
sudo -u plasma-codex -H python3 scripts/plasma-codex-z2-login.py --enroll
```

The prompt collects: known enrolled Z2 host/IP, a verified OpenSSH known_hosts line, password and confirmation (no echo). This creates two `plasma-codex`-owned mode 0600 files in an owner-only 0700 directory:

- `~/.config/plasma/z2-login-smoke.json` (worker login-specific private credentials; username fixed to `xilinx`)
- `~/.config/plasma/z2-login-known_hosts` (the verified **public** Z2 SSH host key)

Existing files are **never overwritten automatically**. No credential strings, private host addresses, file contents, or known-host entries should ever be posted to GitHub or the chat. The normal HIL `z2-dev-credentials.json` file for the previous operator remains unchanged.

**Note:** This worker-specific credential expands the hardware Runner's access capability. GitHub's self-hosted Runner labels are not an authentication boundary. Keep only reviewed, immutable `main` code on this Runner and owner-only fixed commands. The test must not run from a public PR checkout.

## Trigger (only after Gate 2 and private enrollment)

Comment on [Issue #981](https://github.com/physicslu/plasma/issues/981), as the exact repository owner:

```text
/plasma-codex z2-login 981
```

A GitHub-hosted `authorize` job verifies owner/sender/comment body/Issue/default branch, pins reviewed `main` commit SHA, then schedules the fixed `login` job on `SWPC-plasma-codex`. The Runner does not consume Issue comments as commands; no user-supplied shell, arbitrary address or freeform Codex AI prompt is executed.

The run's first steps check Linux account identity and permitted groups; the Python subprocess is bound to the local worker's private credential file. It connects via SSH with **StrictHostKeyChecking=yes**, single password attempt and tight timeout, and runs only `printf 'PLASMA_Z2_SSH_USER='; id -un`. It verifies the remote user equals `xilinx`.

For UART, the script resolves the **FT2232 0403:6010 USB interface 01**, not an arbitrary `ttyUSB0` or reused USB device number, verifies no holder through `fuser`, takes an advisory lock and exclusive TTY mode, and attempts a bounded Linux login with the same private credential. It sends only `printf 'PLASMA_Z2_UART_USER='; id -un` when a recognizable shell prompt appears. No raw console output is logged, and no power/reset/FPGA/DUT commands are sent. UART may be reported BLOCKED/FAIL if already owned by another console or if the prompt layout is not supported—**do not claim success**.

## Live viewing from SWPC

Open a separate SWPC terminal as the trusted operator; the Runner emits the exact per-run command in its Actions log. Substitute the **real run ID**:

```sh
tmux -S /run/plasma-codex/z2-login-<RUN_ID>.sock attach-session -r -t plasma-z2-login-<RUN_ID>
```

This is a **read-only tmux client**; it does not open the serial device again. Detach with `Ctrl+B`, then `D`. The job keeps the tmux session temporarily after completion to allow observation; the socket is deleted at the end of that job. The operator must attach *while the job is active*, not hours afterward. Only sanitized stage status is shown, never target address, usernames beyond expected `xilinx`, passwords, raw UART console text, host-key material or USB serials.

## Acceptance and evidence

- SSH: **PASS** only after actual authenticated connection, validated pinned host key, remote `id -un` output equal `xilinx` and exit status zero.
- UART: **PASS** only after opening correctly mapped FT2232 channel B, a recognizable login/shell prompt and actual remote `id -un` marker equal `xilinx`.
- Missing credentials or trusted host key: **BLOCKED**; no attempt with guessed target.
- Busy/unidentifiable UART: **BLOCKED**; avoid colliding with an existing terminal.
- Timeouts/login failures: **FAIL** or **TIMEOUT**, never converted to PASS.
- Artifacts include **only** sanitized `report.json`, `exit_code` and `SHA256SUMS`, no raw network/serial transcript, IPs, passwords, shell history, or private files.
- Mark overall acceptance PASS only if **both** SSH and UART pass. Any other outcome is incomplete and requires evidence-based diagnosis.

The initial PR-hosted CI executes **offline contracts only**; the exact Issue comment must not be posted before Gate 2. No extra HIL framework, service or device driver is introduced.
