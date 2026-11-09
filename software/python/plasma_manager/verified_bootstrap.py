from __future__ import annotations

import json
import secrets
import threading
import time
from typing import Any, Mapping

from . import bootstrap_request_auth as request_auth
from . import local_enrollment as proto
from .bootstrap import (
    BootstrapCredentialError,
    BootstrapManagerError,
    ManagerBootstrapCoordinator,
    bootstrap_endpoint_for_gateway,
    check_challenge,
)

MAX_GATEWAY_RESPONSE_BYTES = 4 * 1024 * 1024
_REFUSAL_STATUSES = frozenset({400, 401, 403, 404, 409, 503})


class VerifiedManagerBootstrapCoordinator(ManagerBootstrapCoordinator):
    """Manager side of LOM-P2A-2 local enrollment and controller-bound writes.

    Enrollment replaces the retired manual pairing token (Replace-by-Default):

    * ``button``: the Manager posts an ephemeral X25519 public key; the owner
      long-presses the PPU button; ``claim`` then proves the window key that
      only this Manager can derive and unwraps the credential.
    * ``ticket``: the Engineering CLI ticket (or the SD rescue ticket the owner
      wrote) proves the window instead.

    The credential is stored with its controller generation (credential store
    v2) and used automatically afterwards; the owner never types it. Every
    Gateway write is signed with the same P2A-1 proof (G13) and refused if the
    PPU reports a newer generation (replaced) — never retried automatically.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._button_keys: dict[str, tuple[bytes, str, float]] = {}
        self._enrollment_lock = threading.Lock()

    # -- enrollment -----------------------------------------------------------
    def _bootstrap_client(self, alias: str):
        normalized, record = self._entry(alias)
        return normalized, self.client_factory(bootstrap_endpoint_for_gateway(record.endpoint),
                                               self.timeout_s)

    def enrollment(self, alias: str, body: Mapping[str, Any]) -> dict[str, Any]:
        entry, step = body.get("entry"), body.get("step", "start")
        label = body.get("label", "control-station")
        if type(label) is not str or len(label) > proto.MAX_LABEL_CHARS:
            raise ValueError("enrollment label must be a string of at most 64 characters")
        if entry == "button" and step == "start" and set(body) <= {"entry", "step", "label"}:
            return self._button_start(alias, label)
        if entry == "button" and step == "claim" and set(body) <= {"entry", "step", "label"}:
            return self._button_claim(alias, label)
        if entry == "ticket" and set(body) <= {"entry", "ticket", "label"}:
            try:
                ticket = proto.valid_ticket(body.get("ticket"))
            except proto.EnrollmentProtocolError as exc:
                raise ValueError(str(exc)) from exc
            return self._claim(alias, lambda _challenge: proto.ticket_key(ticket), label)
        raise ValueError("enrollment requires entry=button (step start|claim) or entry=ticket")

    def _button_start(self, alias: str, label: str) -> dict[str, Any]:
        normalized, client = self._bootstrap_client(alias)
        private, public = proto.x25519_keypair()
        status, payload = client._json("POST", "/v1/enrollment/button-request",
                                       body={"controller_public": public, "label": label},
                                       timeout_s=20.0)
        if status != 200 or payload.get("ok") is not True:
            return {"ok": False, "ppu_alias": normalized, "state": payload.get("error"),
                    "detail": payload.get("detail"), "upstream_status": status}
        with self._enrollment_lock:
            self._button_keys[normalized] = (
                private, public,
                time.monotonic() + proto.BUTTON_REQUEST_WINDOW_S + proto.ENROLLMENT_WINDOW_S)
        return {"ok": True, "ppu_alias": normalized, "state": "AWAITING_BUTTON",
                "request_id": payload.get("request_id"), "expires_in_s": payload.get("expires_in_s"),
                "instruction": "press and hold the PPU enrollment button for 3 seconds"}

    def _button_claim(self, alias: str, label: str) -> dict[str, Any]:
        normalized, _record = self._entry(alias)
        with self._enrollment_lock:
            held = self._button_keys.get(normalized)
        if held is None or time.monotonic() >= held[2]:
            raise ValueError("no button enrollment request is active for this PPU; start again")
        private, public, _deadline = held

        def key_for(challenge: Mapping[str, Any]) -> bytes:
            if (challenge.get("source") != proto.SOURCE_BUTTON
                    or challenge.get("controller_public") != public):
                # The armed window belongs to another request/entry: never claim it.
                raise BootstrapCredentialError(
                    "the armed enrollment window is not bound to this Control Station")
            try:
                return proto.button_key(private, peer_public=challenge["ppu_public"],
                                        device_id=challenge["device_id"],
                                        request_id=challenge["enrollment_id"],
                                        controller_public=public, ppu_public=challenge["ppu_public"])
            except (KeyError, proto.EnrollmentProtocolError) as exc:
                raise BootstrapManagerError("PPU button enrollment challenge is invalid") from exc

        result = self._claim(alias, key_for, label)
        if result.get("ok"):
            with self._enrollment_lock:
                self._button_keys.pop(normalized, None)
        return result

    def _claim(self, alias: str, key_for, label: str) -> dict[str, Any]:
        normalized, client = self._bootstrap_client(alias)
        status, challenge = client._json("GET", "/v1/enrollment/challenge", timeout_s=20.0)
        if status != 200 or challenge.get("ok") is not True:
            return {"ok": False, "ppu_alias": normalized, "state": challenge.get("error"),
                    "upstream_status": status}
        device_id = challenge.get("device_id")
        if type(device_id) is not str or not proto.DEVICE_RE.fullmatch(device_id):
            raise BootstrapManagerError("PPU enrollment challenge identity is invalid")
        key = key_for(challenge)
        controller_nonce = secrets.token_hex(16)
        request = proto.claim_request(key, challenge, controller_nonce=controller_nonce, label=label)
        status, response = client._json("POST", "/v1/enrollment/claim", body=request, timeout_s=30.0)
        if status != 200 or response.get("ok") is not True:
            return {"ok": False, "ppu_alias": normalized, "state": response.get("error"),
                    "detail": response.get("detail"), "upstream_status": status}
        if response.get("device_id") != device_id or type(response.get("generation")) is not int:
            raise BootstrapManagerError("PPU enrollment response is inconsistent")
        try:
            credential = proto.unwrap_credential(
                key, nonce=response["wrap_nonce"], controller_nonce=controller_nonce,
                generation=response["generation"], wrapped=response["wrapped_credential"])
        except (KeyError, proto.EnrollmentProtocolError) as exc:
            raise BootstrapManagerError("PPU enrollment response is not authenticated") from exc
        self.credentials.set(normalized, device_id, credential, generation=response["generation"],
                             controller_id=response.get("controller_id"))
        # Prove the new credential end to end before reporting success.
        status_payload = self.status(normalized)
        return {
            "ok": True, "ppu_alias": normalized, "state": "ENROLLED",
            "controller_generation": response["generation"], "controller_mode": response["mode"],
            "recovery_blockers": response.get("recovery_blockers", []),
            "enrollment_source": response.get("source"),
            "pairing": status_payload["pairing"],
            "request_authentication": request_auth.SCHEMA,
        }

    # -- explicit recovery actions (RECOVERY_ONLY -> NORMAL) ------------------
    def recovery_action(self, alias: str, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        if body.get("explicit_request") is not True:
            raise ValueError("recovery actions require explicit_request=true")
        _normalized, _record, client, _payload, device_id, token = self._authenticated(alias)
        request = dict(body)
        if request.get("action") == "recovery.complete":
            request["observed_device_id"] = device_id
        return client._json("POST", "/v1/controller/recovery", credential=token,
                            device_id=device_id, body=request, timeout_s=150.0)

    # -- G13: controller-bound Gateway writes ---------------------------------
    def gateway_signer(self, alias: str):
        """``PPUHttpClient.write_signer`` bound to this alias's enrollment."""
        def signer(client: Any, target: str, headers: Mapping[str, str], body: bytes | None,
                   timeout_s: float) -> tuple[int, dict[str, str], bytes]:
            return self.signed_gateway_post(alias, client, target, headers=headers, body=body,
                                            timeout_s=timeout_s)
        return signer

    def signed_gateway_post(self, alias: str, client: Any, target: str, *,
                            headers: Mapping[str, str], body: bytes | None,
                            timeout_s: float) -> tuple[int, dict[str, str], bytes]:
        """POST to the PPU Gateway under the enrolled controller credential.

        Returns the upstream (status, headers, body). A response outside the
        refusal statuses without a valid PPU proof raises (the caller treats it
        as an unknown outcome); an unproven refusal is returned as-is.
        """
        record = self.credentials.record_for(alias)
        status, _headers, raw = client._raw_relay(
            "GET", "/api/auth/challenge", headers={"Accept": "application/json"}, body=None,
            timeout_s=min(timeout_s, 15.0), max_response_bytes=65536)
        try:
            challenge = json.loads(raw) if status == 200 else {}
        except (UnicodeDecodeError, ValueError):
            challenge = {}
        nonce = check_challenge(status, challenge if isinstance(challenge, dict) else {},
                                device_id=record.device_id, generation=record.generation)
        header, context = request_auth.sign_request(
            credential=record.token, method="POST", path=target, body=body,
            device_id=record.device_id, nonce=nonce)
        status, response_headers, response_body = client._raw_relay(
            "POST", target, headers={**headers, "Authorization": header}, body=body,
            timeout_s=timeout_s, max_response_bytes=MAX_GATEWAY_RESPONSE_BYTES,
            extra_response_headers=frozenset({request_auth.RESPONSE_HEADER.lower()}))
        proof = next((value for key, value in response_headers.items()
                      if key.lower() == request_auth.RESPONSE_HEADER.lower()), None)
        if proof is None and status in _REFUSAL_STATUSES:
            return status, response_headers, response_body
        try:
            request_auth.verify_response(credential=record.token, context=context, status=status,
                                         body=response_body, header=proof)
        except request_auth.BootstrapRequestAuthError as exc:
            raise BootstrapManagerError(
                "PPU Gateway response is not authenticated by the enrolled PPU") from exc
        return status, response_headers, response_body
