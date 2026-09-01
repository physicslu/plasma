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
  Plasma Server :19901
  REST Gateway  :19801

Mock PPU B: 4 enabled Sites
  Plasma Server :19902
  REST Gateway  :19802

Plasma Manager  :19880
  manual registry -> PPU A + PPU B
  SQLite observation cache in the temporary runner directory

Vinext/Vite Web :15173
  Control Station product entry
  Production Mode / Fleet enabled
  Engineering Mode
  Manager BFF -> http://127.0.0.1:19880
  same-origin Gateway proxy -> http://127.0.0.1:19801
```

Expected Fleet topology is 2 current PPUs and 12 current/enabled Sites.

For Browser Runtime Acceptance, PPU A's REST Gateway additionally enables the server-side Engineering Mock PPU provider. That provider owns a separate Engineering-only simulation topology:

```text
8 Mock Facilities
  x 4 Mock PPUs per Facility
    -> 2 / 4 / 6 / 8 Sites

Total: 32 Mock PPUs / 160 Sites
```

Each Engineering Mock PPU is a real in-process `PlasmaServer` runtime backed by `MockInterface`. It is not added to the Production Manager registry and does not change the baseline Production/Fleet capacity counts.

## Mock CD baseline checks

`scripts/mock-cd.py` validates:

- both PPU REST Gateways become execution-ready;
- Manager liveness succeeds;
- Manager aggregates both heterogeneous PPUs;
- Fleet summary reports 2 current PPUs and 12 Sites;
- the Vinext/Cloudflare Worker receives Fleet runtime bindings;
- same-origin `/api/fleet` reaches Manager through the loopback-only BFF;
- browser Fleet payload remains sanitized and does not expose registry endpoints, raw errors, or observation database paths;
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

The browser test does **not** use `page.route()` to replace Plasma APIs. The canonical engineering execution path is:

```text
Playwright browser action
  -> Engineering Mode -> Programming
  -> real Plasma Web REST Gateway
  -> EngineeringPPUProvider
  -> selected virtual PlasmaServer
  -> SiteManager / SiteWorker
  -> MockInterface
  -> runtime result / Read download
  -> browser assertion
```

The former Single PPU Programming Console is not part of Browser Runtime Acceptance. EMode Programming owns the single-PPU engineering workflow. `/ppu` is tested only as a compatibility redirect to `/engineering`.

The persistent stack publishes `runtime.json`. The workflow derives the Web URL, Gateway URL, deliberately unreachable Gateway endpoint, and representative Engineering Facility/PPU identity from that runtime contract instead of duplicating runtime values in the Playwright step.

The acceptance scenarios are:

1. **Control Station routing ownership**
   - `/` resolves to `/demo` and renders the product-mode entry;
   - `/ppu` resolves to `/engineering`;
   - neither route exposes the retired `SITE MATRIX / PPU CONTROL` UI.

2. **Engineering Gateway connection state**
   - start from the valid same-origin Engineering path and confirm the provider is online;
   - enter a syntactically valid but unreachable Gateway and confirm EMode reports offline;
   - restore the valid Gateway and confirm clean recovery;
   - verify malformed non-HTTP Gateway input is rejected without reviving the retired direct PPU Console ownership.

3. **EMode per-Site E/P/V/R and Read download**
   - enter `Engineering -> Programming` through the actual Web UI;
   - select the runtime-provided representative Facility and PPU;
   - require Site topology to come from that selected PPU STATUS and contain no `SITE 0`;
   - load a deterministic Programming Image and execute `Erase -> Program -> Verify -> Read` on a Site;
   - observe real outbound requests scoped to `/api/engineering/targets/{facility_id}/{ppu_id}/api/jobs`;
   - require every operation to reach `SUCCESS` through the Python Provider and selected virtual `PlasmaServer`;
   - download the Read result and verify its content.

4. **EMode server-owned Batch**
   - select an arbitrary non-contiguous Site subset in EMode;
   - select multiple operations;
   - require one real `POST /api/batches` whose target identity, Site membership and operation list exactly match operator intent;
   - require the authoritative server-owned Batch to reach `SUCCESS` and selected Site results to reach `PASS`;
   - do not use the retired browser-owned `BatchLifecycle` path.

5. **Programming Image asset reuse/reconnect**
   - exercise the dedicated Engineering asset-cache/reconnect scenario;
   - require server-owned Batch asset semantics and Engineering session continuity;
   - prove the active path does not fall back to legacy direct asset endpoints or direct per-Site Batch orchestration.

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
