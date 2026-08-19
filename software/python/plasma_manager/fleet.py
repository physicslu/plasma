from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from .client import PPUHTTPError, PPUHttpClient
from .config import ManagerConfig, PPURegistryEntry


MANAGER_CONTRACT_VERSION = "1"
MANAGER_SERVICE_NAME = "plasma-manager"
PPU_FLEET_CONTRACT_VERSION = "1"

ClientFactory = Callable[[str, float], Any]


class FleetAggregator:
    """Read-only aggregation over independently operating PPU REST gateways."""

    def __init__(self, config: ManagerConfig, client_factory: ClientFactory = PPUHttpClient) -> None:
        self.config = config
        self.client_factory = client_factory

    def registry_snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": MANAGER_SERVICE_NAME,
            "contract_version": MANAGER_CONTRACT_VERSION,
            "ppus": [
                {"endpoint": entry.endpoint, "alias": entry.alias}
                for entry in self.config.ppus
            ],
        }

    def fleet_snapshot(self) -> dict[str, Any]:
        entries = self.config.ppus
        if entries:
            workers = min(len(entries), 8)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="plasma-manager") as executor:
                ppus = list(executor.map(self._poll_one, entries))
        else:
            ppus = []

        ppu_ids = [
            item["ppu"]["ppu_id"]
            for item in ppus
            if isinstance(item.get("ppu"), dict) and item["ppu"].get("ppu_id")
        ]
        duplicate_ids = {ppu_id for ppu_id, count in Counter(ppu_ids).items() if count > 1}
        if duplicate_ids:
            for item in ppus:
                ppu = item.get("ppu")
                if isinstance(ppu, dict) and ppu.get("ppu_id") in duplicate_ids:
                    item["identity_conflict"] = True
                    item["errors"].append(
                        f"duplicate ppu_id '{ppu['ppu_id']}' reported by multiple registry endpoints"
                    )

        trusted_ppus = [
            item
            for item in ppus
            if isinstance(item.get("ppu"), dict) and not item["identity_conflict"]
        ]
        facilities: dict[str, dict[str, Any]] = {}
        for item in trusted_ppus:
            ppu = item["ppu"]
            facility_id = ppu["facility_id"]
            ppu_id = ppu["ppu_id"]
            facility = facilities.setdefault(
                facility_id,
                {
                    "facility_id": facility_id,
                    "ppu_ids": [],
                    "site_count": 0,
                    "enabled_site_count": 0,
                },
            )
            facility["ppu_ids"].append(ppu_id)
            facility["site_count"] += ppu["site_count"]
            facility["enabled_site_count"] += ppu["enabled_site_count"]

        reachable = sum(item["gateway_live"] for item in ppus)
        ready = sum(item["execution_ready"] for item in ppus)
        reported_sites = sum(item["ppu"]["site_count"] for item in trusted_ppus)
        enabled_sites = sum(item["ppu"]["enabled_site_count"] for item in trusted_ppus)
        degraded = any(item["errors"] or not item["execution_ready"] for item in ppus)

        return {
            "ok": True,
            "service": MANAGER_SERVICE_NAME,
            "contract_version": MANAGER_CONTRACT_VERSION,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "degraded": degraded,
            "summary": {
                "configured_ppus": len(ppus),
                "reachable_ppus": reachable,
                "ready_ppus": ready,
                "identified_ppus": len(trusted_ppus),
                "reported_sites": reported_sites,
                "enabled_sites": enabled_sites,
                "identity_conflicts": len(duplicate_ids),
            },
            "facilities": sorted(facilities.values(), key=lambda item: item["facility_id"]),
            "ppus": ppus,
        }

    def _poll_one(self, entry: PPURegistryEntry) -> dict[str, Any]:
        result: dict[str, Any] = {
            "endpoint": entry.endpoint,
            "alias": entry.alias,
            "gateway_live": False,
            "execution_ready": False,
            "contract_compatible": False,
            "identity_conflict": False,
            "ppu": None,
            "sites": [],
            "errors": [],
        }
        client = self.client_factory(entry.endpoint, self.config.request_timeout_s)
        try:
            _, live = client.liveness()
            if live.get("ok") is not True or live.get("gateway") != "alive":
                raise PPUHTTPError("liveness payload does not declare an alive Gateway")
            result["gateway_live"] = True

            readiness_status, readiness = client.readiness()
            if readiness_status == 503 or readiness.get("execution") != "ready":
                error = readiness.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                result["errors"].append(str(message or "local PPU execution is unavailable"))
                return result
            if readiness.get("ok") is not True:
                raise PPUHTTPError("readiness payload is invalid")
            readiness_ppu_id = readiness.get("ppu_id")
            if not isinstance(readiness_ppu_id, str) or not readiness_ppu_id:
                raise PPUHTTPError("readiness payload is missing ppu_id")
            result["execution_ready"] = True

            _, node = client.node()
            self._validate_node(node)
            if readiness_ppu_id != node["ppu"]["ppu_id"]:
                raise PPUHTTPError("/api/health/ready and /api/node disagree on ppu_id")
            result["contract_compatible"] = True

            _, status = client.status()
            self._validate_status(node, status)
            result["ppu"] = dict(node["ppu"])
            result["sites"] = list(status["sites"])
            return result
        except Exception as exc:
            result["errors"].append(str(exc))
            return result

    @staticmethod
    def _validate_node(node: dict[str, Any]) -> None:
        if node.get("ok") is not True:
            raise PPUHTTPError("/api/node did not return ok=true")
        if node.get("contract_version") != PPU_FLEET_CONTRACT_VERSION:
            raise PPUHTTPError(
                f"unsupported PPU fleet contract version: {node.get('contract_version')!r}"
            )
        if node.get("node_role") != "ppu":
            raise PPUHTTPError("/api/node does not describe a PPU")
        if node.get("manager_required") is not False:
            raise PPUHTTPError("PPU violates standalone-first manager_required=false invariant")
        ppu = node.get("ppu")
        if not isinstance(ppu, dict):
            raise PPUHTTPError("/api/node is missing PPU identity")
        for key in ("ppu_id", "facility_id", "model"):
            if not isinstance(ppu.get(key), str) or not ppu[key]:
                raise PPUHTTPError(f"/api/node is missing ppu.{key}")
        site_count = ppu.get("site_count")
        enabled_site_count = ppu.get("enabled_site_count")
        if isinstance(site_count, bool) or not isinstance(site_count, int) or site_count < 1:
            raise PPUHTTPError("/api/node ppu.site_count must be a positive integer")
        if (
            isinstance(enabled_site_count, bool)
            or not isinstance(enabled_site_count, int)
            or not 0 <= enabled_site_count <= site_count
        ):
            raise PPUHTTPError("/api/node ppu.enabled_site_count is invalid")

    @staticmethod
    def _validate_status(node: dict[str, Any], status: dict[str, Any]) -> None:
        if status.get("ok") is not True:
            raise PPUHTTPError("/api/status did not return ok=true")
        ppu = status.get("ppu")
        sites = status.get("sites")
        if not isinstance(ppu, dict) or not isinstance(sites, list):
            raise PPUHTTPError("/api/status is missing canonical PPU/Site topology")
        for key in ("ppu_id", "facility_id", "model", "site_count", "enabled_site_count"):
            if ppu.get(key) != node["ppu"].get(key):
                raise PPUHTTPError(f"/api/node and /api/status disagree on ppu.{key}")
        if len(sites) != node["ppu"]["site_count"]:
            raise PPUHTTPError("/api/status Site count disagrees with /api/node")
        site_ids = [site.get("site_id") for site in sites if isinstance(site, dict)]
        if len(site_ids) != len(sites) or any(
            isinstance(site_id, bool) or not isinstance(site_id, int) or site_id < 1
            for site_id in site_ids
        ):
            raise PPUHTTPError("/api/status contains invalid canonical site_id values")
        if len(site_ids) != len(set(site_ids)):
            raise PPUHTTPError("/api/status contains duplicate site_id values")
