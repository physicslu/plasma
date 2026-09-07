# H002 — Render / Cloudflare / SWPC Managed PS Qualification

**Date:** 2026-09-07  
**Project:** Plasma Universal Multi-Site IC Programmer  
**Repository:** `physicslu/plasma`  
**Main at handover creation:** `d23ae79ce50e3c94406595f378c8a9e6147c4fbb`  
**Release ID:** `0.1.1-d23ae79ce50e`  
**Status:** Managed control-plane baseline qualified on an x86_64 SWPC PS surrogate; browser Programming/Engineering managed-routing defect remains open  
**Real Z2 admission:** NO  
**PS↔PL admission:** NO  
**HIL admission:** NO  
**Production IC-programming admission:** NO

## 1. Purpose

This handover transfers the current state of the Plasma Render -> Manager -> Cloudflare -> SWPC managed-PPU qualification workstream to a new engineering session.

The key result is that the managed software/network PS path is qualified end-to-end on an x86_64 SWPC Z2-like PS-only surrogate, but the browser Programming / Engineering workflow is not yet consistent with that managed path.

Do not interpret the qualified managed PS route as evidence for real PYNQ-Z2, ARMv7, PL, FPGA, Site electrical behavior, target power, or real IC programming.

## 2. Repository operating contract

`AGENTS.md` remains authoritative and defines exactly two approval gate types:

```text
Request
  -> read-only inspection
  -> Gate 1: Plan Approval
  -> autonomous implementation / validation / PR / CI repair
  -> Gate 2: Merge Approval
  -> merge
  -> any already-approved post-merge deployment/runtime/hardware acceptance
```

There is no third deployment/runtime/hardware approval gate. If this handover conflicts with newer code, tests, configuration, or `AGENTS.md`, the newer repository state wins.

## 3. Canonical Plasma context

Canonical hierarchy:

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Current relevant invariants:

- one PPU supports at most 8 Sites;
- canonical `site_id` is one-based, `1..N`;
- there is no canonical Site 0;
- PLASMA33 protocol version is 3.3;
- Web REST contract version is 3;
- Plasma Gateway is Python stdlib `ThreadingHTTPServer`, not FastAPI and not WebSocket;
- the current SWPC qualification topology is intentionally PS-only with `sites: []`.

## 4. Exact-main release state

The current qualified baseline is exact main:

```text
git_sha    = d23ae79ce50e3c94406595f378c8a9e6147c4fbb
release_id = 0.1.1-d23ae79ce50e
```

Relevant merged work:

| PR | Purpose | Result |
|---|---|---|
| #382 | Release Identity v2 and zero-Site PS-only topology | Merged earlier in this workstream |
| #394 | Render -> SWPC managed PS qualification lab | Merged |
| #396 | Harden SWPC runtime interpreter and readiness | Merged |

PR #396 merge commit is the exact qualified main SHA above.

## 5. SWPC host and runtime baseline

SWPC host:

```text
Ubuntu 22.04.5 LTS
kernel 6.8.0-138-generic
architecture x86_64
repo /storage/projects/plasma
```

System Python is intentionally not the Plasma runtime:

```text
/usr/bin/python3 = Python 3.10.12
```

Plasma-owned runtime interpreter:

```text
/opt/plasma/python/3.12.13/bin/python3
Python 3.12.13
```

Important operational rule: runtime acceptance scripts require Python >= 3.11. Running them with `/usr/bin/python3` fails at `from datetime import UTC` and is an acceptance-environment error, not a managed-path failure.

## 6. SWPC hardened installer qualification

The hardened installer was run from exact main with:

```bash
sudo bash scripts/swpc-z2like-ppu-install.sh \
  --plasma-python /opt/plasma/python/3.12.13/bin/python3 \
  --ppu-id swpc-z2like-01 \
  --facility-id lab
```

Installer transaction result:

```text
PASS
```

Formal install evidence:

```text
/opt/plasma/install/last-swpc-z2like-install.json
```

Recorded evidence includes:

```text
schema_version          1
role                    ppu-surrogate
platform                linux
architecture            x86_64
z2_equivalent           false
product_version         0.1.1
git_sha                 d23ae79ce50e3c94406595f378c8a9e6147c4fbb
release_id              0.1.1-d23ae79ce50e
plasma_python           /opt/plasma/python/3.12.13/bin/python3
plasma_python_version   3.12.13
gateway_bind            127.0.0.1:18080
restricted_ingress      127.0.0.1:18081
hardware_boundary       closed
configured_site_count   0
max_supported_sites     8
```

Services and listeners:

```text
Plasma Server       127.0.0.1:9900
Plasma Gateway      127.0.0.1:18080
Restricted Nginx    127.0.0.1:18081
```

No PPU service is intentionally public-bound.

## 7. Installer hardening semantics from PR #396

The installer now:

- rejects a base/non-venv interpreter (`sys.prefix == sys.base_prefix`);
- requires final Python >= 3.11;
- requires pre-provisioned PyYAML >= 6.0;
- does not mutate the passed interpreter with `pip install`;
- uses the same Plasma interpreter for runtime build and readiness validation;
- performs bounded readiness retry for up to 10 seconds;
- writes formal install evidence only after readiness succeeds.

A previous immutable failed deployment release may remain as rollback evidence and should not be deleted merely to make the host look clean.

## 8. Cloudflare restricted public ingress

Existing Cloudflare routes were preserved. In particular:

```text
plasma.open4th.com -> http://127.0.0.1:5173
```

The managed PPU ingress was added as a separate hostname:

```text
ppu-lab.open4th.com -> http://127.0.0.1:18081
```

Never point the public tunnel directly to the real PPU Gateway at `127.0.0.1:18080`.

The restricted Nginx surface intentionally exposes only:

```text
GET  /api/health/live
GET  /api/health/ready
GET  /api/node
GET  /api/status
POST /api/engineering/diagnostics/loopback
```

Everything else is blocked before the Gateway.

Observed public acceptance:

```text
GET  /api/health/ready      -> HTTP 200
GET  /api/node              -> HTTP 200
GET  /api/status            -> HTTP 200
GET  /api/settings/sites    -> HTTP 404
```

Public PS loopback also returned HTTP 200 with:

```text
ok          = true
endpoint    = ps
source      = ps
payload     = AA==
tx_crc32    = d202ef8d
rx_crc32    = d202ef8d
```

This qualifies the restricted Cloudflare public PS diagnostic path.

## 9. Render Control Station deployment

Render workspace contains a dedicated service:

```text
name = plasma-control-station-lab
url  = https://plasma-control-station-lab.onrender.com
```

It is separate from the older existing Render service and must not be conflated with it.

Qualified deployment properties:

```text
branch       = main
exact commit = d23ae79ce50e3c94406595f378c8a9e6147c4fbb
status       = live
```

Environment relevant to managed PPU routing:

```text
PLASMA_RENDER_PPU_ALIAS=swpc-ppu
PLASMA_RENDER_PPU_ENDPOINT=https://ppu-lab.open4th.com
PYTHON_VERSION=3.12.13
NODE_VERSION=22.22.0
```

Runtime logs confirmed:

```text
Plasma Manager listening on http://127.0.0.1:18180
Control Station Console/BFF listening on 0.0.0.0:10000
swpc-ppu -> https://ppu-lab.open4th.com
```

The Render public service was live after build and deployment.

## 10. Managed PPU registry / observation evidence

Render same-origin manager endpoint:

```text
GET https://plasma-control-station-lab.onrender.com/api/manager/ppu
```

Observed response:

```json
{
  "ok": true,
  "managed": true,
  "configured": true,
  "ppu_alias": "swpc-ppu"
}
```

The browser PPU / Sites page also showed:

```text
Manager Online
Alias         swpc-ppu
PPU ID        swpc-z2like-01
Lifecycle     Validated / Enabled
Status        Online
Execution     ready
Facility      lab
HW Model      SWPC-Z2-SURROGATE
Gateway       https://ppu-lab.open4th.com
```

Therefore Manager registry, PPU identity, and managed observation are qualified.

## 11. Canonical managed PS loopback acceptance

Use the Plasma-owned Python, not `/usr/bin/python3`:

```bash
cd /storage/projects/plasma

/opt/plasma/python/3.12.13/bin/python3 \
  scripts/runtime_acceptance/run.py ps-loopback \
  --base-url https://plasma-control-station-lab.onrender.com/api/manager/ppu \
  --environment render-swpc-managed-ps
```

Observed result:

```text
=== ps-loopback ===
PASS ps-loopback
evidence: artifacts/runtime-acceptance/20260907T073750Z-c57d2cab/ps-loopback.json
```

This is the canonical end-to-end managed PS acceptance for the current software/network baseline.

Qualified path:

```text
SWPC acceptance client
  -> Render Control Station same-origin BFF
  -> Render Manager
  -> Cloudflare HTTPS
  -> SWPC restricted Nginx :18081
  -> Plasma Gateway :18080
  -> Plasma Server :9900
  -> PS diagnostic handler
  -> return
```

## 12. What is PROVEN

The following claims are supported by current evidence:

- exact-main x86_64 SWPC PS-surrogate deployment;
- immutable release identity `0.1.1-d23ae79ce50e`;
- hardened installer transaction and formal evidence emission;
- system-level Plasma Server and Gateway runtime;
- PS-only zero-Site topology;
- `max_supported_sites = 8` while configured `site_count = 0`;
- loopback-only PPU Gateway plus restricted Nginx ingress;
- restricted Cloudflare public surface and negative-route isolation;
- Render Control Station deployment and embedded loopback-only Manager;
- immutable/config-owned Render Manager PPU target;
- Manager registry and PPU observation for `swpc-ppu`;
- public PS loopback through Cloudflare;
- canonical Render-managed PS loopback end-to-end.

## 13. What is NOT PROVEN

Do not claim any of the following from this baseline:

- real PYNQ-Z2 deployment;
- ARMv7 native runtime behavior;
- PYNQ Linux/runtime compatibility;
- PS↔PL communication;
- FPGA execution or timing;
- Site I/O or electrical behavior;
- target power control;
- socket behavior;
- erase/program/verify on a real IC;
- Option-byte or destructive security-transition behavior;
- 8-Site hardware concurrency;
- production readiness.

`z2_equivalent` is explicitly false in the SWPC install evidence.

## 14. Open defect — browser Programming / Engineering managed routing

The infrastructure path is qualified, but browser Programming / Engineering behavior is not fully qualified.

### 14.1 Render Control Station symptom

On the Render Control Station, PPU / Sites managed observation is correct, but the Engineering / Factory Console showed:

```text
Gateway UNREACHABLE · PPU UNKNOWN
Unexpected token '<', "<html> <h"... is not valid JSON
POST /api/engineering/session
```

This strongly indicates that the browser sent:

```text
POST /api/engineering/session
```

and received HTML instead of the expected Plasma JSON response.

Important narrowing evidence:

```text
Render deploy                  PASS
Manager registry               PASS
PPU observation                PASS
Managed PS loopback            PASS
Programming/Engineering UI     FAIL
Engineering session bootstrap  FAIL
```

Therefore this should be investigated as a same-origin BFF / managed-routing integration defect, not as a Cloudflare, SWPC runtime, or Manager-connectivity failure.

### 14.2 Local `plasma.open4th.com` symptom

`plasma.open4th.com` still maps to the SWPC local Web UI on `127.0.0.1:5173` and the page itself loads.

Local evidence:

```text
127.0.0.1:5173 LISTEN by node
GET /engineering -> HTTP 200
```

However the Programming page shows:

```text
PPU OFFLINE
0 Facilities | 0 PPUs | 0 Sites
Engineering PPU provider is not enabled
```

This local UI does not currently have the same managed Manager/BFF runtime as the Render Control Station and should not be used as a second production control-plane architecture.

Do not enable Mock merely to make this screen appear green. That would hide the real managed-routing problem.

## 15. Intended routing architecture

The formal managed control path should remain:

```text
Browser
  -> Control Station same-origin BFF
  -> Manager
  -> configured PPU alias: swpc-ppu
  -> https://ppu-lab.open4th.com
  -> SWPC restricted ingress
  -> Plasma Gateway / Server
```

The browser should not require direct access to `ppu-lab.open4th.com`.

Do not solve the Engineering UI defect by broadening the Cloudflare restricted surface or by exposing port 18080 publicly.

## 16. Recommended next continuation

Start the next session with:

```text
Read repo handover H002 and continue.
```

The first engineering task should be:

> Diagnose and fix the Render Control Station Programming / Engineering managed-routing consistency so `/api/engineering/session` and the rest of the required Engineering workflow use the same same-origin BFF -> Manager -> `swpc-ppu` path already proven by managed PS loopback.

Minimum read-only inspection should cover:

```text
software/web/app/plasma-api.ts
software/web/app/engineering/*
software/web managed bootstrap / BFF routes
software/python/plasma_manager/server.py
software/python/plasma_web/gateway_base.py
software/python/plasma_web/secure_gateway.py
docs/architecture/control-plane-routing-architecture.md
docs/architecture/engineering-programming-workspace.md
docs/deployment/render-swpc-managed-ps-loopback.md
```

Relevant existing test area includes the managed Control Station bootstrap E2E coverage. Verify whether that test proves only bootstrap metadata while missing real Programming-session same-origin routing.

## 17. Acceptance criteria for the next fix

A fix should not be considered complete until all of the following are demonstrated:

```text
1. Render Control Station loads normally.
2. GET /api/manager/ppu returns:
     managed=true
     configured=true
     ppu_alias=swpc-ppu
3. PPU / Sites remains Online and shows swpc-z2like-01.
4. Programming / Engineering no longer reports Gateway UNREACHABLE / PPU UNKNOWN due to route ownership.
5. POST /api/engineering/session returns the expected Plasma JSON contract through the managed path.
6. Browser Engineering requests use same-origin BFF -> Manager routing.
7. Browser does not directly require ppu-lab.open4th.com.
8. Cloudflare restricted public surface remains restricted.
9. /api/settings/sites on ppu-lab remains blocked with 404.
10. Canonical managed ps-loopback remains PASS.
```

If the PS-only zero-Site configuration makes a later Programming workflow intentionally unavailable, the UI must fail with the correct domain-level JSON/state reason, not with HTML parsing errors or routing ambiguity.

## 18. Security and architecture guardrails

Do not:

- expose SWPC `127.0.0.1:18080` publicly;
- repoint `plasma.open4th.com` away from its existing `:5173` origin as an incidental fix;
- broaden `ppu-lab.open4th.com` into a general unrestricted Gateway proxy;
- enable Engineering Mock as a substitute for managed PPU routing;
- allow unauthenticated public mutation of the Render Manager registry;
- claim SWPC is a real Z2;
- claim PS↔PL, FPGA, Site, power, or IC-programming evidence from PS loopback;
- introduce FastAPI or WebSocket as a shortcut; they are not part of the current architecture.

## 19. Useful verification commands

Public restricted PPU checks:

```bash
curl -i https://ppu-lab.open4th.com/api/health/ready
curl -i https://ppu-lab.open4th.com/api/node
curl -i https://ppu-lab.open4th.com/api/status
curl -i https://ppu-lab.open4th.com/api/settings/sites
```

Expected status pattern:

```text
ready            200
node             200
status           200
settings/sites   404
```

Manager bootstrap check:

```bash
curl -i https://plasma-control-station-lab.onrender.com/api/manager/ppu
```

Canonical managed PS acceptance:

```bash
/opt/plasma/python/3.12.13/bin/python3 \
  scripts/runtime_acceptance/run.py ps-loopback \
  --base-url https://plasma-control-station-lab.onrender.com/api/manager/ppu \
  --environment render-swpc-managed-ps
```

## 20. Final handover state

The managed control-plane foundation is sufficiently qualified to stop re-debugging the same infrastructure path without new evidence.

Current decision boundary:

```text
Managed software/network PS baseline      QUALIFIED
Browser PPU / Sites managed observation   QUALIFIED
Browser Programming/Engineering routing   NOT QUALIFIED
Real PYNQ-Z2 / ARMv7                      NOT QUALIFIED
PS↔PL / FPGA                              NOT QUALIFIED
Site / electrical / target power          NOT QUALIFIED
Real IC programming                       NOT QUALIFIED
```

The next session should focus first on the browser Programming/Engineering managed-routing defect. Only after that software control-plane workflow is coherent should this workstream advance to real PYNQ-Z2 native deployment and later PS↔PL / hardware qualification.
