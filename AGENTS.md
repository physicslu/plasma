# Plasma AI Agent Guide

## Repository and Git workflow

- Repository: `physicslu/plasma`.
- `main` is the stable integration branch. Do not develop features directly on `main`.
- Start each task from an up-to-date, clean `main`, then create a focused feature branch.
- Never force-push. Do not commit generated files, credentials, logs, virtual environments, dependencies, or build outputs.
- Before editing, inspect the relevant code, configuration, tests, documentation, and CI workflow.
- Do not use `sudo` unless the user explicitly authorizes it.

## Project layout and toolchains

- `software/python/`: Python control plane, TCP server, Web Gateway, CLI, interfaces, and tests.
- `software/web/`: React / TypeScript / Vite programmer console.
- `pl/`: FPGA RTL, constraints, tests, and Vivado build scripts.
- Python requires version 3.11 or newer. On SWPC, the project virtual environment is `software/python/.venv`.
- Web development uses Node.js 22. Do not run `npm update` or upgrade dependencies unless the user explicitly requests it.
- Do not modify or upgrade the Vivado installation.

## Validation commands

Run checks relevant to every changed area.

Python:

```bash
cd software/python
.venv/bin/python -m pytest -q
```

Web:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

FPGA repository checks that do not require Vivado:

```bash
python3 -m unittest discover -s pl/tests -v
```

Do not install packages, update lockfiles, or upgrade dependencies merely to run checks without explicit approval.

## Runtime environment on SWPC

- Plasma Server: `127.0.0.1:9900`.
- Python Web Gateway: `127.0.0.1:18080`.
- Vite development server: `127.0.0.1:5173`.
- TCP port `8080` belongs to Apache/Nextcloud. Do not bind to it, stop it, or change Apache/Nextcloud.
- Tailscale Web URL: `https://swpc.tail820e64.ts.net`.
- Tailscale API URL: `https://swpc.tail820e64.ts.net:8443`.
- The current prototype enables CH0 and CH1 with the Mock Interface. Do not present mock operations as physical-device programming.
- Do not stop running Plasma services or change Tailscale Serve unless the task explicitly requires it.

## Change discipline and handoff

- Keep changes within the user-approved scope; do not modify unrelated Python, TypeScript, FPGA, configuration, or generated files.
- Do not independently use `sudo`, run `npm update`, upgrade dependencies, force-push, stop Apache/Nextcloud, or alter Vivado.
- After code changes, run the relevant unit/build/integration checks in proportion to the change.
- Before requesting review, run `git status`, `git diff --check`, and `git diff`.
- At completion, report:
  - changed files and the purpose of each;
  - tests/checks run and their results;
  - the resulting `git diff` or a concise review of it;
  - any known mismatch, risk, or check that was not run.
