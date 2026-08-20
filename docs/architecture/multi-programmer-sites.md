# Historical Multi-Programmer / Multi-Site Naming

This document records a **retired historical naming model**. It is not a current runtime contract. Current architecture is defined by [`ppu-facility-sites.md`](./ppu-facility-sites.md) and [`domain-naming-migration.md`](./domain-naming-migration.md).

The previous hierarchy was:

```text
Site -> Programmer -> Channel
```

It was retired because `Site` was overloaded to mean a deployment location while the IC-programming domain also needs **Programming Site** for an independently controlled programming position.

The canonical hierarchy is now:

```text
Facility -> PPU -> Site
```

where:

- **Facility** = deployment / administrative location.
- **PPU** = Plasma Programming Unit, one physical programming device and local execution node.
- **Site** = Programming Site, one independently controlled programming position inside a PPU.
- **Socket** = physical IC fixture attached to a Site; it is not the Site identity itself.

Canonical Site identity is one-based:

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

Current canonical wire contract is **Plasma Protocol v3.3 / `PLASMA33`** with one-based `site_id`.

Historically, older protocol revisions used zero-based Channel identity. Those mappings are useful only to understand old commits and artifacts; they are not accepted by the current development runtime and must not be reintroduced as a compatibility layer without a new explicit requirement and versioned migration plan.

Do not introduce new product/domain code using the retired Programmer/Channel vocabulary.
