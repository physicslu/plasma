from __future__ import annotations

from typing import Any

from .bootstrap import (
    BootstrapCredentialError,
    BootstrapManagerError,
    ManagerBootstrapCoordinator,
    _device_id_from_status,
    _valid_token,
)


class VerifiedManagerBootstrapCoordinator(ManagerBootstrapCoordinator):
    """Manager Bootstrap coordinator with device-authenticated pairing.

    Pairing proves the supplied credential WITHOUT transmitting it: the Manager
    sends one MACed ``GET /v1/status`` under a fresh PPU nonce for the observed
    ``device_id`` and persists the credential only when the PPU answers with a
    valid response MAC for that exact request and the authenticated status
    names the same device. A spoofed endpoint can neither learn the credential
    nor produce the response proof.

    Manual credential entry remains until LOM-P2A-2 replaces it with local
    enrollment; this class only removes credential exposure on the wire.
    """

    def pair(self, alias: str, token: str) -> dict[str, Any]:
        validated_token = _valid_token(token)
        normalized, _record, client, _payload, device_id = self._live(alias)
        try:
            status, payload = client.status(validated_token, device_id)
        except BootstrapCredentialError:
            raise
        except BootstrapManagerError as exc:
            raise BootstrapCredentialError(
                "Bootstrap pairing token could not be verified against the registered device"
            ) from exc
        bootstrap = payload.get("bootstrap") if status == 200 else None
        if (
            status != 200
            or not isinstance(bootstrap, dict)
            or bootstrap.get("state") != "bootstrap_ready"
            or _device_id_from_status(payload) != device_id
        ):
            raise BootstrapCredentialError(
                "Bootstrap pairing token could not be verified against the registered device"
            )
        self.credentials.set(normalized, device_id, validated_token)
        pairing = dict(self.credentials.public_state(normalized))
        pairing["device_verified"] = True
        return {
            "ok": True,
            "ppu_alias": normalized,
            "pairing": pairing,
            "token_verification": "verified_before_persistence",
            "request_authentication": "plasma.ppu.bootstrap-request-auth.v1",
        }
