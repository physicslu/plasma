# Plasma GitHub Actions Mock CD

Mock CD is a software deployment/runtime acceptance layer between source/browser CI and real integration-host deployment.

It answers:

> If this commit is launched as an ephemeral Plasma software stack on a clean GitHub-hosted Ubuntu runner, do the runtime components discover each other and expose the expected runtime contracts?

It does **not** answer whether SWPC systemd deployment, public tunnel/TLS, Z2, FPGA, electrical I/O, or real IC programming works.

## Validation layers

```text
Source CI
  -> Browser CI with mocked API responses
  -> Mock CD full-stack smoke
  -> Mock CD Browser Runtime Acceptance
  -> SWPC deployment + plasmactl verify ...
  -> Human UI acceptance
  -> Z2 / FPGA / real-target acceptance when applicable
```

A lower layer never proves the next layer.

## Baseline topology

The workflows start only ephemeral localhost processes on the GitHub-hosted runner:

```text
Mock PPU A: 8 enabled Sites
  Plasma Server  :19901
  Plasma Gateway :19801

Mock PPU B: 4 enabled Sites
  Plasma Server  :19902
  Plasma Gateway :19802

Plasma Manager  :19880
  manual registry -> PPU A + PPU B
  SQLite observation cache in the temporary runner directory

Vinext/Vite Web :15173
  Control Station product entry
  Production Mode / Fleet enabled
  Engineering Mode
  Manager BFF -> http://127.0.0.1:19880
  same-origin Plasma Gateway proxy -> http://127.0.0.1:19801
```

Expected Fleet topology is 2 current PPUs and 12 current/enabled Sites.

For Browser Runtime Acceptance, PPU A's Plasma Gateway additionally enables the server-side Engineering Mock PPU provider. That provider owns a separate Engineering-only simulation topology:

```text
8 Mock Facilities
  x 4 Mock PPUs per Facility
    -> 2 / 4 / 6 / 8 Sites

Total: 32 Mock PPUs / 160 Sites
```

Each Engineering Mock PPU is a real in-process `PlasmaServer` runtime backed by `MockInterface`. It is not added to the Production Manager registry and does not change the baseline Production/Fleet capacity counts.

## Mock CD baseline checks

`scripts/mock-cd.py` validates:

- both PPU Plasma Gateways become execution-ready;
- Manager liveness succeeds;
- Manager aggregates both heterogeneous PPUs;
- Fleet summary reports 2 current PPUs and 12 Sites;
- the Vinext/Cloudflare Worker receives Fleet runtime bindings;
- same-origin `/api/fleet` reaches Manager through the loopback-only BFF;
- browser Fleet payload remains sanitized and does not expose registered Plasma Gateway Endpoints, raw errors, or observation database paths;
- `/` resolves to the Control Station product entry;
- `/demo` remains the product-mode entry;
- `/fleet` resolves Production Mode;
- `/engineering` resolves Engineering Mode;
- legacy `/ppu` resolves to Engineering Mode and never exposes `SITE MATRIX / PPU CONTROL`;
- all ephemeral processes remain alive through acceptance.

The harness terminates its own process groups on success or failure and prints service log tails when acceptance fails.

## Baseline machine-readable artifact

Every baseline run attempts to create:

```text
artifacts/mock-cd/acceptance.json
```

The GitHub workflow uploads the whole `artifacts/mock-cd/` directory as `mock-cd-acceptance`, including process logs. The JSON contains the commit, overall result, stack summary, and named scenario results.

## Browser Runtime Acceptance

`.github/workflows/mock-cd-browser.yml` drives the actual Control Station through Playwright while the persistent harness `scripts/mock-cd-browser-stack.py` keeps the same Mock CD stack alive.

The browser test does **not** use `page.route()` to replace Plasma APIs. Since U10 the Console is managed-only and the canonical execution path is the Managed Lifecycle:

```text
Playwright browser action (EMode Programming / PMode Factory Console)
  -> same-origin Console BFF (/api/manager/...)
  -> Plasma Manager ProgrammingBatchCoordinator
  -> real PPU Bootstrap: Resource Set activation (B1/B2/B3, first use only),
     Reservation, Job Binding
  -> Mock PPU Runtime (Plasma Server + MockInterface) via its G13 Gateway
  -> Manager Batch / run receipt (incl. Read output)
  -> browser assertion + Manager evidence read through the same BFF
```

Specs only observe Browser requests (`page.on`) and read Manager evidence (`GET /api/manager/programming/batches/<id>`, `GET /api/manager/registry/<alias>/bootstrap/programming/runs/<run_id>`). The retired Browser-owned paths (`/api/batches`, `/api/engineering/...`, `/api/programming-assets`, direct `/api/jobs`) are recorded only to prove they stay unused. `/ppu` is tested only as a compatibility redirect to `/engineering`.

The persistent stack publishes `runtime.json` (schema 3). Besides the Web URL it carries `managed`: the Manager URL, the two managed Mock PPUs (`ppu-a` 8 Sites, `ppu-b` 4 Sites), the Mock Route (ICPN, Flash Base / Size) and `harness_control_url`, a test-harness-only switch (`POST /ppus/<alias>/offline|online`) that stops and restarts one PPU's Gateway. The workflow exports these as `MOCK_CD_*` environment variables. Every PPU starts with no Active Set: its first Batch that carries an Image runs B1/B2/B3, later Batches reuse it. An Image-less Batch (Erase-only, Read) never activates.

The acceptance scenarios are:

1. **Control Station routing ownership**
   - `/` resolves to `/demo`; `/ppu` resolves to `/engineering`;
   - neither route exposes the retired `SITE MATRIX / PPU CONTROL` UI.

2. **Manager-managed PPU offline / recovery**
   - the Console has no Gateway URL / Connect control;
   - the harness takes a managed PPU's Gateway offline: EMode shows `PPU OFFLINE` and Start is disabled while the Manager Registry stays ONLINE;
   - back online: `PPU ONLINE`, Start enabled again, nothing submitted.

3. **EMode per-Site E/P/V/R and Read download**
   - Erase, Program and Verify each run as their own one-Site Manager Batch with exactly that operation and reach PASS in the Manager receipt;
   - READ on the Site row is its own Read Batch over address / length (the Route's whole Flash);
   - the Browser download is named by the Manager's Read output and its bytes re-hash to the receipt SHA256 (Image at Flash Base, the rest erased).

4. **EMode Batch membership**
   - a non-contiguous Site subset × multiple operations is ONE `POST /api/manager/programming/batches` whose Target Set and operations match operator intent;
   - the Manager Batch and every Site run reach PASS.

5. **1 MiB Programming Image reuse**
   - three Batches (the third after a Console reload) each carry the Image once, for both Sites;
   - Manager evidence: every Job binds the same Image; the Resource Set is activated at most once (Batch `resource_activation`, B1/B2/B3) and later Batches reuse it (`resource_reuse`, Active Set generation 1).

6. **PMode multi-PPU Batch**
   - one Manager Batch over `ppu-a` + `ppu-b` with a shared Image (E/P/V) and one Erase-only Batch complete on both PPUs, each with its own Job / Binding;
   - ABORT is whole-Batch STOP QUEUING: started Jobs complete PASS, queued Cycles are never submitted. Known intermittent pre-existing BFF bug: the stop relay (GET Batch, then POST stop to the HTTP/1.0 Manager) can lose the POST (503 `manager_unavailable`); the test stays strict.

7. **Mock runtime settings** are written through the Manager relay (the G13 Gateway refuses an unsigned direct write) and EMode System Configuration shows the applied revision.

8. **Programming Job parity**: PMode and EMode present one Programming Job contract at 1200 px and 1680 px.

The Playwright configuration preserves trace, screenshot, video, HTML report, and JSON report on failure. The workflow emits:

```text
artifacts/mock-cd-browser/browser-acceptance.json
```

and uploads the complete directory as:

```text
mock-cd-browser-acceptance
```

A Browser Runtime Acceptance PASS still does not mean SWPC, Z2, FPGA, socket, electrical I/O, or real IC programming passed.

## Security and deployment boundary

Both Mock CD workflows intentionally use `ubuntu-latest`, no self-hosted runner, no SSH, no deployment secrets, no `systemctl`, and no `plasmactl deploy`.

They must never silently evolve into real SWPC or Z2 deployment mechanisms. Real deployment remains an explicit human approval gate. A future private deployment workflow/self-hosted runner is a separate design and security decision.

## Planned extensions

Separate scenarios may later add deterministic PPU outage -> stale, Manager restart -> SQLite restore, recovery -> current, a real authenticated `RealPPUProvider`, and additional failure injection. These should extend the artifact schemas rather than changing the meaning of existing PASS results.
