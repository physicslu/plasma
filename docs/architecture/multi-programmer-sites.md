# Legacy Multi-Programmer / Multi-Site Naming

This document records the retired naming model. Current architecture is defined by [`ppu-facility-sites.md`](./ppu-facility-sites.md) and [`domain-naming-migration.md`](./domain-naming-migration.md).

The previous hierarchy was:

```text
Site -> Programmer -> Channel
```

It is deprecated because `Site` was overloaded to mean a deployment location while the IC-programming domain also needs **Programming Site** for an independently controlled programming position.

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

Protocol v3.2 is the canonical wire contract and uses `PLASMA32` plus one-based `site_id`.

Protocol v3.1 remains only as an explicit compatibility adapter:

```text
v3.1 channel_id 0 -> canonical / v3.2 site_id 1
v3.1 channel_id 1 -> canonical / v3.2 site_id 2
...
```

Do not interpret legacy `channel_id` as numerically identical to `site_id`, and do not introduce new product/domain code using the retired Programmer/Channel vocabulary.
