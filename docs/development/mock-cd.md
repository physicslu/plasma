# Plasma GitHub Actions Mock CD

Mock CD is a software deployment/runtime acceptance layer between source/browser CI and real integration-host deployment.

It answers:

> If this commit is launched as an ephemeral Plasma software stack on a clean GitHub-hosted Ubuntu runner, do the runtime components discover each other and expose the expected read-only Fleet contract?

It does **not** answer whether SWPC systemd deployment, public tunnel/TLS, Z2, FPGA, electrical I/O, or real IC programming works.

## Validation layers

```text
Source CI
  -> Browser CI
  -> Mock CD
  -> SWPC deployment + plasmactl verify ...
  -> Human UI acceptance
  -> Z2 / FPGA / real-target acceptance when applicable
```

A lower layer never proves the next layer.

## Baseline topology

The workflow starts only ephemeral localhost processes on the GitHub-hosted runner:

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
```

Expected Fleet topology is 2 current PPUs and 12 current/enabled Sites.

## Baseline checks

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

## Machine-readable artifact

Every run attempts to create:

```text
artifacts/mock-cd/acceptance.json
```

The GitHub workflow uploads the whole `artifacts/mock-cd/` directory as `mock-cd-acceptance`, including process logs. The JSON contains the commit, overall result, stack summary, and named scenario results.

A representative successful result is:

```json
{
  "schema_version": 1,
  "commit": "<sha>",
  "result": "PASS",
  "stack": {
    "ppus": 2,
    "sites": 12,
    "manager": "read-only",
    "web_bff": true
  },
  "scenarios": {
    "full_stack_smoke": "PASS",
    "two_ppu_heterogeneous_topology": "PASS",
    "worker_binding": "PASS",
    "browser_contract_sanitization": "PASS",
    "public_demo_routing": "PASS"
  }
}
```

## Security and deployment boundary

Mock CD intentionally uses `ubuntu-latest`, no self-hosted runner, no SSH, no deployment secrets, no `systemctl`, and no `plasmactl deploy`.

It must never silently evolve into a real SWPC or Z2 deployment mechanism. Real deployment remains an explicit human approval gate. A future private deployment workflow/self-hosted runner is a separate design and security decision.

## Planned extensions

After the baseline is stable, separate scenarios may add deterministic PPU outage -> stale, Manager restart -> SQLite restore, recovery -> current, and programming-operation smoke. These should extend the same artifact schema rather than changing the meaning of baseline PASS.
