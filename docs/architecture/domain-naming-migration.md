# Domain Naming Migration Policy

Canonical Plasma product/domain terms are:

```text
Facility -> PPU -> Site
```

The migration is staged so product/domain vocabulary can become consistent without silently breaking the Plasma v3.1 wire protocol.

## Canonical now

- Product/UI: `PPU`, `SITE n`, `Facility`.
- Configuration: `ppu`, `facility_id`, `sites`, `max_supported_sites`, `max_queue_depth_per_site`.
- Python domain types: `PPUConfig`, `SiteConfig`, `SiteState`, `SiteManager`, `SiteWorker`.
- Python canonical modules: `plasma_server.site_manager` and `plasma_server.site_worker`.
- Plasma Server scheduling and logs use Site terminology internally.
- STATUS exposes canonical `ppu` and `sites` views.
- Plasma Web REST Gateway accepts `site_id` / `?site=`.
- CLI uses `--site` and renders `SITE<n>`; `--channel` is a legacy alias.
- Job audit logs are written under `SITE<n>` and include `site_id`.
- New read-back outputs use `read_SITE<n>_<section>.bin`.

## Compatibility retained

- Plasma protocol v3.1 continues to use the wire field `channel_id`.
- `JobRequest` / `JobResult` retain `channel_id` as their protocol-storage field and expose `site_id` as the domain alias.
- Legacy configuration names (`programmer`, deployment `site_id`, `channels`, `max_supported_channels`, `max_queue_depth_per_channel`) can still be loaded or passed where explicitly supported.
- Legacy Python aliases remain available: `ProgrammerConfig`, `ChannelConfig`, `ChannelState`, `ChannelManager`, `ChannelWorker`.
- `plasma_server.channel_manager` and `plasma_server.channel_worker` remain compatibility shims; new code must import the Site modules.
- STATUS temporarily also emits `programmer` and `channels` views.
- E4001/E4002/E4003 values are unchanged. Python now uses `ErrorCode.SITE_INVALID`, `SITE_DISABLED`, and `SITE_BUSY`; the serialized v3.1 `error_type` strings remain `CHANNEL_*` for compatibility.
- Job JSONL includes canonical `site_id` and a temporary legacy `channel_id` field.
- Job logs are canonical under `SITE<n>` and are temporarily mirrored to legacy `CH<n>` directories for migration compatibility.

## Explicit boundary

This naming work does **not** change:

- Plasma protocol version or frame format.
- The v3.1 `channel_id` wire key.
- Existing stable PPU IDs.
- FPGA / PL logic.
- Hardware behavior.
- Deployment topology.

A future protocol-version migration may replace `channel_id` on the wire. That must be handled as an explicit protocol change, not hidden inside a naming cleanup.
