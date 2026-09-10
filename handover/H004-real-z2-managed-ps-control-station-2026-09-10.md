# H004 — Real Z2 Managed PS / Control Station Handover

Date: 2026-09-10
Status: Current engineering handover

This handover captures the Real PYNQ-Z2 PS qualification state, macOS Control Station managed-routing findings, the PR #450 fix, and the remaining CI-cache work. Repository code/tests remain authoritative if they differ from this document.

## 1. Product architecture boundary

```text
Control Station
  -> Console / BFF
  -> Plasma Manager
  -> Manager registry alias
  -> Plasma Gateway on PYNQ-Z2
  -> Plasma Server / PS
  -> future PL / Site / target IC
```

The current real-hardware qualification is intentionally staged. A PASS at PS level does not imply PL, Site hardware, target power, real IC programming, or 8-Site concurrency readiness.

## 2. Real PYNQ-Z2 baseline

Observed target baseline:

```text
Architecture     armv7l
Distribution     PynqLinux 3.0 / Ubuntu 22.04
glibc            2.35
systemd          249
System Python    3.10.4
PYNQ             3.1.1
Z2 address       192.168.2.99
Gateway port     18080
PPU ID           z2-dev-01
Facility ID      lab
```

Current lab topology:

```text
Mac Control Station
  -> Mac Internet Sharing / private Ethernet
  -> PYNQ-Z2 192.168.2.99:18080
```

This topology is acceptable for functional qualification only. Production networking should not depend on ad-hoc Internet Sharing.

## 3. Z2 PS runtime qualification

The installed Z2 PS kit used Plasma Python 3.12.13 under `/opt/plasma/python/3.12.13/` without replacing the PYNQ/System Python.

Observed qualification result:

```text
Real Z2 ARMv7 PS runtime/profile    PASS
Local PS diagnostic loopback       PASS
Plasma Python 3.12.13               PASS
plasma-server.service               active
plasma-web.service                  active
Gateway                             http://192.168.2.99:18080
```

Canonical readiness semantics are:

```text
gateway   = alive
execution = ready
```

The `z2-ps` verifier is PS-only. It does not load a bitstream, access PL, enable Sites, change target power, or program an IC.

## 4. Real Managed PS path qualification

The Mac Control Station successfully enrolled the Z2 through EMode:

```text
Add PPU
  alias    = z2
  endpoint = http://192.168.2.99:18080

Validate & Enable
  -> PPU online
  -> lifecycle validated / enabled
  -> execution ready
```

The managed PS loopback initially failed with:

```text
Manager PPU selection is unavailable
```

Investigation proved:

```text
selected-ppu-alias file = z2
HOME                    = /Users/gordon
Console process env     = PLASMA_MANAGER_PPU_ALIAS=
```

After fully reloading the Console LaunchAgent, the process contained:

```text
PLASMA_MANAGER_PPU_ALIAS=z2
```

Managed PS loopback then passed.

Therefore the following path is functionally qualified:

```text
Mac Browser
  -> Control Station Console / BFF
  -> Plasma Manager
  -> registry alias z2
  -> Real PYNQ-Z2 Gateway
  -> Plasma Server
  -> PS loopback
  -> return path
```

Qualification status:

```text
Real Z2 PS                    QUALIFIED
Managed Control Station path  QUALIFIED
PS <-> PL                     NOT YET QUALIFIED
Site hardware                 NOT YET QUALIFIED
Real IC programming           NOT YET QUALIFIED
8-Site concurrency            NOT YET QUALIFIED
```

## 5. PR #450 — runtime Managed PPU selection fix

PR:

```text
#450 Fix runtime Managed PPU selection
```

Merged on 2026-09-10.

Merge commit:

```text
7d21ed04061d62943b2f8b50eaed2dbe17511dd7
```

The defect was architectural, not a Z2 transport failure: the packaged Console/BFF froze the Managed PPU alias from `PLASMA_MANAGER_PPU_ALIAS` at process startup. Add / Validate & Enable did not make the runtime command target usable without manual alias-file editing and a full Console reload.

The merged design now keeps the Manager registry authoritative for alias -> Gateway Endpoint resolution and supports runtime Managed PPU selection. The Browser selects only a registry alias, never an arbitrary destination URL.

Key behavior:

```text
single commissioned PPU
  -> may be resolved automatically

multiple commissioned PPUs
  -> explicit Managed-operation selection required

selection
  -> runtime-capable
  -> no manual selected-ppu-alias edit
  -> no Console restart required
```

Security boundary:

- no direct-Gateway browser fallback;
- Manager remains endpoint owner;
- selection is by alias only;
- fail closed when selection is ambiguous.

CI for PR #450 passed Web validation, browser runtime acceptance, Control Station runtime packaging, repository contracts, and macOS installer acceptance before merge.

## 6. macOS Control Station package notes

The current pilot installer is unsigned / non-notarized. It uses external validated runtimes and installs per-user launchd agents.

Default local endpoints:

```text
Console   http://127.0.0.1:18000
Manager   http://127.0.0.1:18180
```

A manual installation was used successfully during this qualification after the package upgrade path initially reported an installer script error. Treat installer upgrade robustness as separate deployment debt from the managed-routing defect fixed by PR #450.

## 7. PR #451 — Z2 ARMv7 Python CI cache

PR:

```text
#451 Cache verified Z2 ARMv7 Python runtime
```

Current state at handover creation:

```text
open       yes
mergeable  yes
draft      yes
```

The core Z2 release workflow passes:

```text
z2-python-runtime  PASS
z2-ps-kit          PASS
repository contracts PASS
```

The cache design:

```text
cache key includes
  cache schema
  runner OS
  ARMv7
  Ubuntu 22.04
  Python 3.12.13
  pinned Python source SHA-256
  workflow / build-recipe hash

cache HIT
  -> skip expensive CPython QEMU build only
  -> still verify artifact + SHA-256
  -> still install on fresh Ubuntu 22.04 ARMv7 userspace
  -> still execute runtime smoke

cache MISS
  -> build
  -> verify
  -> trusted main may save cache
```

Trust rule: cache is disposable performance state, not a release source or trust root. Pull requests may restore but must not publish shared executable cache state.

One unrelated CI lane currently fails because the checked-in Device Catalog contains 563 entries while older tests still expect 544. Do not misattribute that failure to the cache change.

## 8. Next engineering step

The next hardware milestone is formal Plasma PS <-> PL loopback/protocol qualification.

Do not repeat the earlier LED exercise. That only proved basic PS -> AXI -> PL bring-up.

Target next path:

```text
Control Station
  -> Manager
  -> Real Z2 Gateway
  -> PS
  -> formal PL loopback block/protocol
  -> PS
  -> Manager
  -> Control Station
```

The acceptance should prove deterministic request/response framing, timeout/error behavior, and a production-usable PS/PL software-hardware contract. Only after that should Site electrical qualification and real-IC programming move forward.

## 9. Recommended continuation prompt

```text
Read repo handover H004 and continue from the Real Z2 Managed PS qualification. First confirm current repository and PR state. Then continue PR #451 or propose the formal Plasma PS<->PL loopback milestone according to AGENTS.md gates.
```
