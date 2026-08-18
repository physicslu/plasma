# Domain Naming and Identity Migration Policy

Canonical Plasma product/domain hierarchy is:

```text
Facility -> PPU -> Site
```

Canonical Site identity is **one-based**:

```text
SITE 1 .. SITE N
```

There is no canonical `SITE 0`.

## Canonical v3.2 contract

- Product/UI: `PPU`, `SITE n`, `Facility`.
- Configuration: `ppu`, `facility_id`, `sites`, `max_supported_sites`, `max_queue_depth_per_site`.
- Canonical YAML `sites:` IDs are `1..N`.
- Python domain types: `PPUConfig`, `SiteConfig`, `SiteState`, `SiteManager`, `SiteWorker`.
- Python canonical modules: `plasma_server.site_manager` and `plasma_server.site_worker`.
- Plasma Server scheduling, job state, canonical audit logs and read-back outputs use one-based `site_id`.
- Protocol v3.2 uses `PLASMA32`, `protocol_version: "3.2"`, and one-based `site_id`.
- v3.2 STATUS exposes `ppu` and `sites` only.
- Plasma Web REST Gateway canonical API accepts one-based `site_id` / `?site=`.
- New Web requests send `site_id` only; they do not dual-send `channel_id`.
- CLI uses one-based `--site` and renders `SITE<n>`.
- Canonical Job audit logs are written under `SITE<n>` and contain `site_id` only.
- Read-back outputs use `read_SITE<n>_<section>.bin`.
- E4001/E4002/E4003 retain their numeric values; v3.2 names are `SITE_INVALID`, `SITE_DISABLED`, `SITE_BUSY`.

## v3.1 compatibility boundary

Protocol v3.1 remains temporarily supported as an explicit adapter, not as a second canonical identity model:

```text
v3.1                      canonical / v3.2
PLASMA31                  PLASMA32
channel_id 0      ->      site_id 1
channel_id 1      ->      site_id 2
...
channel_id N-1    ->      site_id N
```

Compatibility behavior:

- Server accepts v3.1 `PLASMA31` frames and returns v3.1 responses to v3.1 requests.
- v3.1 uses zero-based `channel_id`; v3.2 uses one-based `site_id`.
- v3.1 STATUS retains `programmer/channels`; v3.2 STATUS uses `ppu/sites`.
- v3.1 errors serialize E4001/E4002/E4003 as `CHANNEL_INVALID`, `CHANNEL_DISABLED`, `CHANNEL_BUSY`.
- Legacy YAML rooted at `channels:` is treated as zero-based and translated once at config load.
- `ChannelManager` is a v3.1 compatibility facade; canonical runtime code uses `SiteManager`.
- Legacy Python aliases/import paths remain only where needed for migration compatibility.
- Canonical `SITE<n>` Job logs are temporarily mirrored to legacy `CH<n-1>` paths. Canonical JSONL contains only `site_id`; legacy mirror JSONL contains only `channel_id`.
- Read-back binaries are not duplicated under legacy `read_CH*` names.

## Boundary rules

New code must not:

- create or display `SITE 0`;
- treat `site_id == channel_id` as an invariant;
- dual-send `site_id` and `channel_id` in v3.2 requests;
- expose `programmer/channels` from a v3.2 STATUS response;
- write `channel_id` into canonical Site audit records.

The following are intentionally unchanged by this migration:

- Existing stable PPU IDs.
- FPGA / PL RTL logic and physical hardware behavior.
- Deployment topology.
- Python distribution identity `plasma-multichannel`.

Removing the v3.1 adapter entirely is a separate deprecation/removal decision and must not be hidden inside unrelated cleanup work.
