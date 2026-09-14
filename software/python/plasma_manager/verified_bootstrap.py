from __future__ import annotations

from typing import Any

from .bootstrap import BootstrapCredentialError, ManagerBootstrapCoordinator, _valid_token


PAIR_PROBE_REJECTION = "size must be an integer in range 1.."
PAIR_PROBE_BODY = {"size": 0, "sha256": "0" * 64}


class VerifiedManagerBootstrapCoordinator(ManagerBootstrapCoordinator):
    """Manager Bootstrap coordinator with device-authenticated pairing.

    Pairing proves the supplied bearer token against the Bootstrap service before
    persisting it. The probe deliberately submits an invalid zero-sized upload:
    Bootstrap authenticates the bearer first, then rejects the request before any
    upload state is created. Only that exact authenticated validation rejection is
    accepted as proof; every other response fails closed.
    """

    def pair(self, alias: str, token: str) -> dict[str, Any]:
        validated_token = _valid_token(token)
        normalized, _record, client, _payload, _device_id = self._live(alias)
        status, payload = client.create_upload(validated_token, PAIR_PROBE_BODY)
        if (
            status != 409
            or payload.get("error") != "bootstrap_request_rejected"
            or not isinstance(payload.get("message"), str)
            or not payload["message"].startswith(PAIR_PROBE_REJECTION)
        ):
            raise BootstrapCredentialError(
                "Bootstrap pairing token could not be verified against the registered device"
            )
        result = super().pair(normalized, validated_token)
        result["pairing"]["device_verified"] = True
        return result
