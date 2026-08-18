# Domain Naming Migration Policy

Canonical Plasma product/domain terms are now:

```text
Facility -> PPU -> Site
```

This migration is intentionally staged.

## Changed now

- Configuration accepts canonical `ppu`, `facility_id`, and `sites` names.
- Python domain types expose `PPUConfig`, `SiteConfig`, `SiteManager`, and `SiteState`.
- STATUS exposes canonical `ppu` and `sites` views.
- Plasma Web REST Gateway accepts `site_id` / `?site=`.
- Server logs use `ppu_id`, `facility_id`, and `site_id` for newly migrated events.

## Compatibility kept now

- Plasma protocol v3.1 continues to use the wire field `channel_id`.
- Legacy `programmer`, deployment `site_id`, and `channels` configuration can still be loaded.
- Legacy Python aliases remain available: `ProgrammerConfig`, `ChannelConfig`, `ChannelManager`, `ChannelState`.
- STATUS temporarily also emits `programmer` and `channels` views.
- Existing `CHANNEL_*` error codes are not renumbered.

## Not changed in this migration

- Protocol version / frame format.
- Existing stable PPU IDs.
- Web Console visible terminology and layout.
- FPGA / PL logic.
- Hardware behavior.
- Deployment topology.

The visible Web Console vocabulary should be migrated only after the canonical backend/domain contract is validated, with Visual Regression protecting the accepted layout.
