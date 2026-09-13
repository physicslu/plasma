# SWPC Z2-like Configured Mock Programming

Status: integration qualification path for the canonical SWPC Z2-like PPU topology. This is **software/mock Programming only**. It does not qualify PYNQ-Z2, ARMv7, PL/FPGA, Site electrical behavior, target power, OpenOCD, or real IC programming.

## Purpose

The Secure Managed Programming Ingress establishes the protected Render -> SWPC transport path, but transport alone does not create an Engineering Programming provider.

The legacy Engineering Mock Provider is deliberately unsuitable for Z2-like qualification because it creates an independent demo topology:

```text
8 Facilities
32 PPUs
160 Sites
```

That would make PPU/Sites and Programming describe different systems.

The configured provider instead binds the Engineering Programming REST contract to the same canonical PPU that already owns Site Desired state and normal Plasma execution:

```text
Render Z2Like Console/BFF
  -> Manager
  -> Cloudflare Access protected managed ingress
  -> SWPC 127.0.0.1:18082
  -> SWPC 127.0.0.1:18080 Plasma Gateway
  -> ConfiguredMockEngineeringPPUProvider
  -> SWPC 127.0.0.1:9900 Plasma Server
  -> /etc/plasma/ppu.yaml
  -> lab / swpc-z2like-01 / SITE1..SITE8
  -> MockInterface
```

There is one Facility, one PPU, and exactly the Sites declared by the canonical PPU configuration. No independent Mock `PlasmaServer` processes are created.

## Safety boundary

The configured provider is explicit and fail-closed.

It starts only when the Gateway receives:

```text
--engineering-configured-mock
```

At startup it validates:

- the canonical PPU Server address is loopback;
- every configured Site uses `interface: mock`;
- the local Plasma Server identity matches the configured PPU identity.

If any Site becomes `openocd` or `fpga`, configured Mock Programming activation is rejected. This prevents a capability intended only for the SWPC software surrogate from silently becoming a remote real-hardware programming path.

The legacy `--engineering-mock` provider is not enabled and is mutually exclusive with the configured provider.

## Execution model

The provider does not own the local Plasma Server lifecycle. Jobs use the normal Plasma Protocol connection to the independently managed `plasma-server.service`.

For Program/Verify:

```text
Browser upload
  -> Engineering session Asset cache
  -> normalize binary Image
  -> Plasma Protocol binary payload
  -> existing local Plasma Server
  -> configured Site MockInterface
```

The process-local shared Mock blob store used by the 32-PPU demo provider is not used. This matters because the Gateway and Plasma Server are separate systemd processes.

Server-side Batch uses the durable provider path rather than the process-coupled Mock recovery model, because restarting the Gateway does not restart the independent Plasma Server.

Read resolves Main Flash from the configured Site's `mock.flash_size`; when absent it uses the normal MockInterface default of 256 KiB.

## SWPC activation

Prerequisites:

1. the SWPC `swpc-z2like` profile is installed from a release containing this provider;
2. `/etc/plasma/ppu.yaml` contains only Mock Sites;
3. the normal Z2-like verification passes;
4. the separate secure managed ingress on `127.0.0.1:18082` is already installed.

Activate Programming explicitly:

```bash
cd "$PLASMA_REPO"
sudo bash scripts/plasmactl-swpc-z2like-programming install
```

Verify:

```bash
sudo bash scripts/plasmactl-swpc-z2like-programming verify
```

Expected result:

```text
PASS: configured local Mock Programming provider is active: lab/swpc-z2like-01/8
execution boundary: existing canonical PPU/Sites only; legacy 32-PPU demo topology is not instantiated
qualification boundary: software/mock only; no Z2/ARMv7/PL/FPGA/Site electrical/real-IC claim
```

The activation is implemented as an explicit systemd drop-in for `plasma-web.service`. Removal is equally explicit:

```bash
sudo bash scripts/plasmactl-swpc-z2like-programming remove
```

Once Programming has been explicitly enabled, normal release upgrades are one operation:

```bash
sudo ./scripts/plasmactl deploy swpc-z2like
```

The top-level SWPC profile orchestrator reads the declared add-on state before deployment, upgrades the immutable base runtime, then regenerates and verifies the configured Mock Programming activation against the new base evidence. Operators do **not** need to manually repeat `plasmactl-swpc-z2like-programming install` after every base upgrade. Fresh installs remain fail-closed: the orchestrator preserves previously enabled capabilities but never enables Programming merely because the base profile exists.

## Render acceptance

After SWPC activation, the existing protected managed path should expose:

```text
GET /api/engineering/targets
```

with the following topology:

```text
provider: configured_mock
facility_count: 1
ppu_count: 1
site_count: 8

lab
└── swpc-z2like-01
    ├── SITE1
    ├── SITE2
    ├── SITE3
    ├── SITE4
    ├── SITE5
    ├── SITE6
    ├── SITE7
    └── SITE8
```

The Programming workspace must therefore show the same PPU identity as PPU/Sites instead of the legacy 32-PPU demo catalog.

For the first acceptance, keep only the already-enabled SITE1 selected and upload a small binary Image. Run:

```text
Erase -> Program -> Verify
```

Required evidence:

1. Facility `lab` and PPU `swpc-z2like-01` are selectable;
2. Site list matches canonical Desired/Actual state;
3. binary Programming Asset upload/check succeeds;
4. SITE1 Erase -> Program -> Verify reaches terminal PASS;
5. progress is observable through the normal Job status path;
6. Cancel remains functional;
7. `PPU / Sites` remains Online/Healthy with eight configured Sites;
8. `18081` diagnostics ingress remains unchanged;
9. unauthenticated requests to the managed Cloudflare hostname remain denied.

A PASS supports only this claim:

```text
Render managed control
-> authenticated managed ingress
-> canonical SWPC Z2-like PPU
-> configured Mock Site execution
```

It is not evidence of real Z2, OpenOCD, PL, target power, reset safety, socket electrical behavior, or real IC programming.