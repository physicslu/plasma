# Legacy Multi-Programmer / Multi-Site Naming

This document has been superseded by the canonical Plasma domain model in [`ppu-facility-sites.md`](./ppu-facility-sites.md).

The previous hierarchy:

```text
Site -> Programmer -> Channel
```

is deprecated because `Site` was overloaded to mean a deployment location while the IC-programming domain also uses **Programming Site** for an independently controlled programming position.

The canonical hierarchy is now:

```text
Facility -> PPU -> Site
```

where:

- **Facility** = deployment / administrative location.
- **PPU** = Plasma Programming Unit, one physical programming device.
- **Site** = Programming Site, one independently controlled programming position inside a PPU.

For compatibility, Plasma protocol v3.1 still uses the wire field `channel_id` for the local Site ID. See the canonical architecture document for the migration contract and alias policy.
