from __future__ import annotations

from plasma_manager.client import PPUHTTPError
from plasma_manager.config import ManagerConfig, PPURegistryEntry
from plasma_manager.fleet import FleetAggregator


class PSOnlyClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def liveness(self):
        return 200, {"ok": True, "service": "plasma-web-rest-gateway", "gateway": "alive"}

    def readiness(self):
        return 200, {
            "ok": True,
            "gateway": "alive",
            "execution": "ready",
            "ppu_id": "z2-dev-01",
        }

    def node(self):
        return 200, {
            "ok": True,
            "contract_version": "1",
            "node_role": "ppu",
            "manager_required": False,
            "ppu": {
                "ppu_id": "z2-dev-01",
                "facility_id": "lab",
                "model": "PYNQ-Z2",
                "display_name": "Z2 Dev 01",
                "site_count": 0,
                "enabled_site_count": 0,
                "capabilities": {
                    "max_supported_sites": 8,
                    "operations": ["erase", "program", "verify", "read"],
                },
            },
            "links": {
                "status": "/api/status",
                "jobs": "/api/jobs",
                "liveness": "/api/health/live",
                "readiness": "/api/health/ready",
            },
        }

    def status(self):
        _, node = self.node()
        return 200, {"ok": True, "ppu": dict(node["ppu"]), "sites": []}


def test_ps_only_zero_site_ppu_is_contract_compatible() -> None:
    config = ManagerConfig(
        request_timeout_s=0.5,
        ppus=(PPURegistryEntry(endpoint="http://192.168.2.99:18080", alias="z2"),),
    )

    snapshot = FleetAggregator(config, PSOnlyClient).fleet_snapshot()
    item = snapshot["ppus"][0]

    assert snapshot["degraded"] is False
    assert snapshot["summary"]["configured_ppus"] == 1
    assert snapshot["summary"]["reachable_ppus"] == 1
    assert snapshot["summary"]["ready_ppus"] == 1
    assert snapshot["summary"]["identified_ppus"] == 1
    assert snapshot["summary"]["reported_sites"] == 0
    assert snapshot["summary"]["enabled_sites"] == 0
    assert item["gateway_live"] is True
    assert item["execution_ready"] is True
    assert item["contract_compatible"] is True
    assert item["identity_conflict"] is False
    assert item["ppu"]["ppu_id"] == "z2-dev-01"
    assert item["ppu"]["site_count"] == 0
    assert item["ppu"]["capabilities"]["max_supported_sites"] == 8
    assert item["sites"] == []
    assert item["errors"] == []


def test_negative_site_count_remains_invalid() -> None:
    _, node = PSOnlyClient("http://z2", 0.5).node()
    node["ppu"]["site_count"] = -1

    try:
        FleetAggregator._validate_node(node)
    except PPUHTTPError as exc:
        assert "non-negative integer" in str(exc)
    else:
        raise AssertionError("negative ppu.site_count must fail closed")
