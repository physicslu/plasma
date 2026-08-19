from __future__ import annotations

from plasma_manager.client import PPUHTTPError, PPUTransportError
from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.fleet import FleetAggregator


class ResponseErrorClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def liveness(self):
        raise PPUHTTPError("/api/health/live returned invalid JSON")


class TransportErrorClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def liveness(self):
        raise PPUTransportError("/api/health/live request failed: timed out")


def _snapshot(client_factory):
    config = ManagerConfig(
        request_timeout_s=0.5,
        ppus=(PPURegistryEntry(endpoint="http://ppu-a"),),
    )
    return FleetAggregator(config, client_factory).fleet_snapshot()["ppus"][0]


def test_reachable_http_response_error_is_not_reported_as_network_outage():
    item = _snapshot(ResponseErrorClient)

    assert item["transport_state"] == "reachable"
    assert item["gateway_live"] is False
    assert item["execution_state"] == "unknown"
    assert "invalid JSON" in item["errors"][0]


def test_transport_exception_is_reported_as_unreachable():
    item = _snapshot(TransportErrorClient)

    assert item["transport_state"] == "unreachable"
    assert item["gateway_live"] is False
    assert item["execution_state"] == "unknown"
    assert "timed out" in item["errors"][0]
