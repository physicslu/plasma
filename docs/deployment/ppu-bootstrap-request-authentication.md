# PPU Bootstrap mutual request authentication (LOM-P2A-1)

> Status: **Implemented on main (`3c2145f3d`), Host-only and hosted-CI verified.** Deployment plan: [synchronized runbook](ppu-lom-p2a1-synchronized-deployment-runbook.md) (not authorized). Policy: [ADR-0008 Local Owner Mode](../adr/0008-local-owner-mode.md). Not deployed to any PPU by this change; real Z2 behavior is **NOT_RUN** until a separately approved deployment.
> Wire contract: `plasma.ppu.bootstrap-request-auth.v1`. PPU verifier: `scripts/ppu_bootstrap_request_auth.py`. Manager client mirror: `software/python/plasma_manager/bootstrap_request_auth.py` (byte-identical, enforced by `software/python/tests/test_ppu_bootstrap_request_auth.py`).

## Why

The former scheme sent `Authorization: Bearer <paired credential>` in clear over the private commissioning HTTP link, and the Manager learned the device identity from an anonymous `GET /v1/status`. Any host answering at the registered endpoint could therefore harvest the credential (and with it the Owner Operation Authorization key), and an anonymous status could not prove which device answered. This replaces Bearer directly (Replace-by-Default); there is no fallback.

## Protocol

1. Client: `GET /v1/auth/challenge` (anonymous) → `{ok, schema, device_id, nonce, expires_in_s:60}`. The nonce is 128-bit, single-use, memory-only (dropped on Bootstrap restart), at most 256 outstanding.
2. Client checks `device_id` against the paired device (Manager) or pins it for the session (SWPC CLI), then sends the real request with
   `Authorization: PLASMA-PPU-HMAC-V1 device_id=<id>,nonce=<32 hex>,cnonce=<32 hex>,mac=<64 hex>`,
   where `mac = HMAC-SHA256(K_req, "<schema>\nrequest\n<METHOD>\n<request-target>\n<device_id>\n<nonce>\n<cnonce>\n<SHA256(body)>")` and `K_req = HMAC-SHA256(credential, "<schema>/request-key")`.
3. PPU, **before reading the body**: strict header syntax, `device_id` equals its own identity, nonce issued and unexpired — the nonce is consumed here, so a nonce never admits a second attempt. Then it reads the bounded body and verifies the MAC in constant time. Any failure → `401 {"ok":false,"error":"unauthorized"}` with no side effect; missing credential → `503 control_not_provisioned`.
4. Every response to an authenticated request carries `X-Plasma-PPU-Response-Auth: v1 mac=<64 hex>` over `"<schema>\nresponse\n<METHOD>\n<target>\n<device_id>\n<nonce>\n<cnonce>\n<request mac>\n<status>\n<SHA256(response body)>"` with `K_resp = HMAC-SHA256(credential, "<schema>/response-key")`. Clients accept a success, receipt or status only with a valid proof. The SWPC CLI reports an unproven POST response as `OUTCOME_UNKNOWN` (never retried) and an unproven read as a failure; the Manager raises `BootstrapManagerError` on its existing transport-failure path. Unproven 401/503 are treated only as refusals.

The request target is the **PPU-local** path. The managed `z2like-demo` ingress strips `/__plasma/bootstrap` and adds one allowlisted `GET /v1/auth/challenge` route; the MAC therefore remains valid through it.

Anonymous reads (`/v1/health`, `/v1/status`, `/v1/assets`, `/v1/deployment`) remain available for discovery. When an `Authorization` header is present on `/v1/status`, `/v1/assets` or `/v1/deployment`, it must verify and the response is MACed. All `POST` routes require authentication.

## Consumers migrated in the same change

| Consumer | Change |
| --- | --- |
| `scripts/ppu-bootstrap-service.py` | `_authenticate` replaces `_authorized`; `/v1/auth/challenge`; response MAC in `_json`; `security.request_authentication` in status |
| `software/python/plasma_manager/bootstrap.py` | `BootstrapHttpClient` signs/verifies; `_authenticated` proves the paired device with a MACed status (no anonymous identity); `status()` reports `device_authenticated`; `token_for` → `credential_for` |
| `software/python/plasma_manager/verified_bootstrap.py` | Pairing proof = one MACed status for the observed device (the zero-size upload probe is retired) |
| `software/python/plasma_manager/client.py` | `relay(..., extra_response_headers=)` so only the Bootstrap client receives the proof header |
| `scripts/ppu_deploy_api.py`, `scripts/ppu_path2_hardware_baseline.py` | SWPC CLI and Path 2 direct baseline sign/verify; transport returns response headers |
| `scripts/plasmactl-z2like-demo-managed-ingress`, `scripts/z2like-demo-nginx-ephemeral.py` | allowlisted challenge route |
| `scripts/ppu-bootstrap-installer.py`, `.github/workflows/ppu-bootstrap.yml` | ships/compiles `ppu_bootstrap_request_auth.py` |

## What this does not change or claim

- The Owner Operation Authorization (`ppu_owner_authorization.py`), its key derivation, B1/B2/B3, journals, Active Set, Site leases, SAFE_OFF, SEALED and `OUTCOME_UNKNOWN` rules are unchanged.
- **No confidentiality.** Request/response bodies remain readable on the link; this proves integrity and credential possession only. Production TLS is still NOT_QUALIFIED.
- **Enrollment (LOM-P2A-2).** The credential is now the current controller credential created by local enrollment ([spec](../development/opf-local-owner-mode-p2a0-enrollment-spec.md)); `provision-token` and manual pairing are retired. `GET /v1/auth/challenge` additionally reports the non-secret `controller_generation`, and the same proof binds Gateway (`:18080`) writes through the controller admission socket (G13). Refused requests report `{"error":"unauthorized","code":"CONTROLLER_UNAUTHENTICATED","controller_generation":N}`.
- A Bootstrap restart drops outstanding nonces; a client retries the read-only challenge, never a write whose outcome is unknown.
- Challenge flooding can evict nonces (bounded DoS on the controlled link); it cannot authenticate a request.

## Deployment compatibility

PPU Bootstrap and every client must move together: an old Bootstrap rejects the new header (401) and a new Bootstrap rejects Bearer (401). Both fail closed without side effects. Updating Z2 and the SWPC Manager requires a separately approved deployment; until then the Z2 keeps the previous Bearer behavior and this change is NOT_RUN on hardware.
