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
  Fleet enabled
  Manager BFF -> http://127.0.0.1:19880
  PPU Console default Gateway -> http://127.0.0.1:19801
```

Expected Fleet topology is 2 current PPUs and 12 current/enabled Sites.

For Browser Runtime Acceptance, PPU A's REST Gateway additionally enables the server-side Engineering Mock PPU provider. That provider owns a separate Engineering-only simulation topology:

```text
3 Mock Facilities
  x 4 Mock PPUs per Facility
    -> 2 / 4 / 6 / 8 Sites

Total: 12 Mock PPUs / 60 Sites
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
- public demo routing still resolves `/ -> /demo`, `/demo`, `/ppu`, and `/fleet`;
- all ephemeral processes remain alive through acceptance.

The harness terminates its own process groups on success or failure and prints service log tails when acceptance fails.

## Baseline machine-readable artifact

Every baseline run attempts to create:

```text
artifacts/mock-cd/acceptance.json
```

The GitHub workflow uploads the whole `artifacts/mock-cd/` directory as `mock-cd-acceptance`, including process logs. The JSON contains the commit, overall result, stack summary, and named scenario results.

## Browser Runtime Acceptance

`.github/workflows/mock-cd-browser.yml` drives the actual PPU Web console through Playwright while the persistent harness `scripts/mock-cd-browser-stack.py` keeps the same Mock CD stack alive.

The browser test does **not** use `page.route()` to replace Plasma APIs. Its required local-PPU path is:

```text
Playwright browser action
  -> Web UI
  -> real Plasma Web REST Gateway
  -> real Plasma Server
  -> MockInterface
  -> runtime result / Read download
  -> browser assertion
```

The Engineering path is also real and unmocked:

```text
Playwright browser action
  -> Engineering -> Programming
  -> real Plasma Web REST Gateway
  -> EngineeringPPUProvider
  -> selected virtual PlasmaServer
  -> SiteManager / SiteWorker
  -> MockInterface
  -> runtime result / Read download
  -> browser assertion
```

The persistent stack publishes `runtime.json`. The workflow derives the Web URL, Gateway URL, deliberately unreachable Gateway endpoint, local PPU identity/site count, and representative Engineering Facility/PPU identity from that runtime contract instead of duplicating those runtime values in the Playwright step.

The acceptance scenarios are:

1. **Gateway connection state**
   - start from the valid Mock Gateway and confirm connected/ready;
   - enter a syntactically valid but unreachable Gateway and confirm offline/unreachable;
   - require the operator log to contain the attempted endpoint exactly once for that outage transition;
   - restore the valid Gateway and confirm clean recovery to connected/ready;
   - verify malformed non-HTTP Gateway input is rejected separately without replacing the active valid connection.

2. **Per-Site operator controls and Read download**
   - use the enabled Site count published by the runtime contract rather than embedding one fixed loop boundary in the workflow;
   - for every enabled Site, click the individual `Erase`, `Program`, `Verify`, and `Read` controls;
   - inspect the browser's real outbound `POST /api/jobs` request and require each click to dispatch exactly to the intended Site and operation;
   - require every operation to be accepted by the real Gateway/Server path and reach `SUCCESS`;
   - program a deterministic 256-byte firmware pattern, verify it, then Read the same range;
   - capture the real browser download event for every Site;
   - require the download name `read_SITE<n>_flash.bin`, exact byte length, and exact byte-for-byte content match.

3. **Site batch membership and operation selection**
   - click every enabled Site's add/remove-from-batch checkbox and prove the selection changes cleanly;
   - do not impose parity, adjacency, or fixed Site-number rules on batch membership;
   - exercise representative arbitrary non-empty subsets: one Site, two widely separated Sites, a non-contiguous three-Site set, `N-1` Sites, and all enabled Sites, deduplicated for smaller topologies;
   - include mixed odd/even and non-contiguous selections when the topology permits them;
   - change membership between runs so stale selection cannot leak forward;
   - combine Site membership with one or multiple operation checkboxes and inspect the browser's real outbound `POST /api/jobs` requests without mocking or fulfilling them;
   - require the resulting dispatch multiset to equal `selected Sites × selected operations` exactly, which also proves unselected Sites and unselected operations receive no jobs.

4. **Engineering server catalog and selected-PUU execution**
   - require the Gateway's real `/api/engineering/targets` catalog to report 3 Facilities / 12 PPUs / 60 Sites;
   - enter `Engineering -> Programming` through the actual Web UI;
   - select the runtime-provided representative Facility and 6-Site PPU;
   - require the rendered Site topology to come from that selected PPU STATUS and contain no `SITE 0`;
   - load deterministic firmware and execute `Erase -> Program -> Verify -> Read` on the last Site of that selected PPU;
   - observe real outbound requests scoped to `/api/engineering/targets/{facility_id}/{ppu_id}/api/jobs`;
   - require every operation to reach `SUCCESS` through the Python Provider and selected virtual `PlasmaServer`;
   - download the Read result and require exact byte length and byte-for-byte firmware match.

This fourth scenario specifically proves that Engineering Facility/PPU selection is not a React-only mock and that changing the target identity changes the Python execution target.

For `N` enabled Sites there are `2^N - 1` possible non-empty subsets. CI intentionally uses representative boundary and non-contiguous subsets rather than exhaustively executing all combinations; exhaustive 8-Site coverage would require 255 membership combinations before considering operation combinations.

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
