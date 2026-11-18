"""Host-only tests: mocked Manager GET, no PPU, Z2, FPGA, network or DUT."""
from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from plasma_cli.api import FleetError, manager_batch, manager_deployment_status, manager_fleet
from plasma_cli.main import main, observe_deployments, select_fleet
from plasma_cli.programming import verify_batch_receipt
from plasma_cli.targets import parse_targets


def fleet():
    return {
        "ok": True,
        "observed_at": "2026-11-18T00:00:00Z",
        "degraded": False,
        "ppus": [
            {
                "alias": "z2", "gateway_live": True, "execution_ready": False,
                "identity_conflict": False, "errors": [],
                "ppu": {"ppu_id": "physical-z2", "facility_id": "lab"},
                "sites": [{"site_id": 1, "enabled": True}, {"site_id": 2, "enabled": False}],
            },
            {
                "alias": "second", "gateway_live": True, "execution_ready": True,
                "identity_conflict": False, "errors": [],
                "ppu": {"ppu_id": "physical-second", "facility_id": "lab"},
                "sites": [{"site_id": 14, "enabled": True}],
            },
        ],
    }


@pytest.mark.parametrize("raw", [
    ["z2:0"], ["z2:1,1"], ["z2:1", "z2:2"], ["z2:"],
    ["z2:-1"], ["z2:1,"], ["z2:1:2"], [":1"], [" z2:1"], ["z2:true"],
])
def test_invalid_target_set_fails_closed(raw):
    with pytest.raises(ValueError):
        parse_targets(raw)


def test_manager_alias_maximum_length_matches_registry_contract():
    alias = "a" * 128
    assert parse_targets([f"{alias}:1"])[0].ppu_alias == alias
    with pytest.raises(ValueError, match="PPU_ALIAS"):
        parse_targets([f"{alias}b:1"])


def test_any_site_topology_and_multi_ppu():
    targets = parse_targets(["z2:1,2", "second:14"])
    result, complete = select_fleet(fleet(), targets, all_ppus=False)
    assert complete
    assert [x["ppu_alias"] for x in result["ppus"]] == ["z2", "second"]
    assert [x["site_id"] for x in result["ppus"][1]["sites"]] == [14]
    assert result["ppus"][0]["execution_ready"] is False
    assert result["ppus"][0]["status"] == "OBSERVED"  # Never HIL PASS.


def test_missing_ppu_or_site_does_not_pass():
    result, complete = select_fleet(fleet(), parse_targets(["unknown:1", "z2:3"]), all_ppus=False)
    assert not complete
    assert result["ppus"][0]["status"] == "NOT_FOUND"
    assert result["ppus"][1]["status"] == "NOT_VERIFIED"
    assert result["ppus"][1]["missing_site_ids"] == [3]


def test_unreachable_ppu_is_not_verified():
    bad = fleet()
    bad["ppus"][0]["gateway_live"] = False
    result, complete = select_fleet(bad, parse_targets(["z2:1"]), all_ppus=False)
    assert not complete
    assert result["ppus"][0]["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("change", [
    {"degraded": True}, {"degraded": None}, {"ppus": []},
])
def test_all_fails_closed_for_unhealthy_or_empty_fleet(change):
    snapshot = fleet()
    snapshot.update(change)
    _, complete = select_fleet(snapshot, (), all_ppus=True)
    assert not complete


def test_all_fails_closed_for_offline_or_conflicting_ppu():
    snapshot = fleet()
    snapshot["ppus"][1]["identity_conflict"] = True
    _, complete = select_fleet(snapshot, (), all_ppus=True)
    assert not complete
    snapshot["ppus"][1]["identity_conflict"] = False
    snapshot["ppus"][1]["gateway_live"] = False
    _, complete = select_fleet(snapshot, (), all_ppus=True)
    assert not complete


def test_all_rejects_duplicate_ppu_observations():
    snapshot = fleet()
    snapshot["ppus"].append(dict(snapshot["ppus"][0]))
    with pytest.raises(FleetError, match="duplicate"):
        select_fleet(snapshot, (), all_ppus=True)


def test_all_returns_fleet_without_programming():
    result, complete = select_fleet(fleet(), (), all_ppus=True)
    assert complete and len(result["ppus"]) == 2


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _Opener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def open(self, request, *, timeout):
        self.request = request
        assert timeout == 5.0
        return _Response(json.dumps(self.payload).encode())


def test_manager_transport_only_uses_get():
    opener = _Opener(fleet())
    with patch("plasma_cli.api.build_opener", return_value=opener):
        result = manager_fleet("http://127.0.0.1:18280")
    assert result["ok"] is True
    assert opener.request.get_method() == "GET"
    assert opener.request.full_url == "http://127.0.0.1:18280/api/fleet"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://user:pass@host", "http://host/api/fleet",
    "http://host/?x=1", "http://host/#test", "http://host:invalid",
])
def test_unsafe_manager_url_does_not_open_network(url):
    with patch("plasma_cli.api.build_opener", side_effect=AssertionError("network forbidden")):
        with pytest.raises(FleetError):
            manager_fleet(url)


def test_cli_diagnose_targets_and_no_write(capsys):
    with patch("plasma_cli.main.manager_fleet", return_value=fleet()) as get:
        status = main(["diagnose", "--target", "z2:1,2", "--target", "second:14"])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["ppus"][1]["sites"][0]["site_id"] == 14
    get.assert_called_once()


def test_cli_error_does_not_claim_pass(capsys):
    with patch("plasma_cli.main.manager_fleet", side_effect=FleetError("unavailable")):
        status = main(["diagnose", "--all"])
    assert status == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False

BATCH_ID = "a" * 32


def recorded_batch():
    return {
        "batch_id": BATCH_ID, "state": "finished", "outcome": "PASS",
        "journal_persisted": True,
        "targets": [{"ppu_alias": "z2", "site_ids": [1, 2]},
                    {"ppu_alias": "second", "site_ids": [14]}],
        "units": [
            {"ppu_alias": "z2", "site_id": 1, "status": "FINISHED",
             "outcome": "PASS", "attempts": [{"job_id": "job1"}]},
            {"ppu_alias": "z2", "site_id": 2, "status": "FINISHED",
             "outcome": "PASS", "attempts": [{"job_id": "job2"}]},
            {"ppu_alias": "second", "site_id": 14, "status": "FINISHED",
             "outcome": "PASS", "attempts": [{"job_id": "job3"}]},
        ],
    }


def test_receipt_uses_manager_report_only_and_supports_multiple_ppus():
    result, success = verify_batch_receipt(
        recorded_batch(), parse_targets(["second:14", "z2:2"]))
    assert success and result["manager_reported_pass"]
    assert result["evidence_kind"] == "MANAGER_REPORTED_BATCH_ONLY"
    assert [(x["ppu_alias"], x["site_id"]) for x in result["sites"]] == [
        ("second", 14), ("z2", 2)]


@pytest.mark.parametrize("outcome", ["PARTIAL", "FAIL", "OUTCOME_UNKNOWN", "BLOCKED", None])
def test_receipt_never_passes_when_batch_does_not_pass(outcome):
    record = recorded_batch()
    record["outcome"] = outcome
    _, success = verify_batch_receipt(record, parse_targets(["z2:1"]))
    assert not success


@pytest.mark.parametrize(("field", "value"), [
    ("state", "running"),
    ("state", "completed"),
    ("journal_persisted", False),
    ("journal_persisted", None),
])
def test_receipt_requires_finished_and_durable_journal(field, value):
    record = recorded_batch()
    record[field] = value
    result, success = verify_batch_receipt(record, parse_targets(["z2:1"]))
    assert not success
    assert result["manager_reported_pass"] is False


def test_receipt_unfinished_unit_cannot_be_misreported_as_pass():
    record = recorded_batch()
    record["units"][0]["status"] = "NOT_RUN"
    result, success = verify_batch_receipt(record, parse_targets(["second:14"]))
    assert not success
    assert not result["manager_reported_pass"]


def test_receipt_cannot_hide_peer_failure_by_filtering_target():
    record = recorded_batch()
    record["units"][0]["outcome"] = "FAIL"
    _, success = verify_batch_receipt(record, parse_targets(["second:14"]))
    assert not success


def test_receipt_denies_missing_target_and_duplicate_units():
    record = recorded_batch()
    with pytest.raises(FleetError, match="absent"):
        verify_batch_receipt(record, parse_targets(["z2:4"]))
    record["units"].append(dict(record["units"][0]))
    with pytest.raises(FleetError, match="duplicate"):
        verify_batch_receipt(record, ())


def test_receipt_get_uses_exact_id_and_never_post():
    opener = _Opener({"ok": True, "batch": recorded_batch()})
    with patch("plasma_cli.api.build_opener", return_value=opener):
        result = manager_batch("http://127.0.0.1:18280", BATCH_ID)
    assert result["batch_id"] == BATCH_ID
    assert opener.request.get_method() == "GET"
    assert opener.request.full_url.endswith("/api/programming/batches/" + BATCH_ID)


@pytest.mark.parametrize("bad", ["", "../z2", "A" * 32, "f" * 33, "x" * 32])
def test_receipt_bad_id_denied_before_io(bad):
    with patch("plasma_cli.api.build_opener", side_effect=AssertionError("no I/O")):
        with pytest.raises(FleetError, match="Batch ID"):
            manager_batch("http://127.0.0.1:18280", bad)


def test_receipt_cli_readonly(capsys):
    with patch("plasma_cli.main.manager_batch", return_value=recorded_batch()) as get:
        status = main(["program", "receipt", "--batch-id", BATCH_ID,
                       "--target", "z2:1,2"])
    assert status == 0
    output = json.loads(capsys.readouterr().out)
    assert output["manager_reported_pass"] is True
    assert output["batch_id"] == BATCH_ID
    get.assert_called_once()

def test_deployment_status_reads_bootstrap_without_mutation():
    opener = _Opener({
        "ok": True, "ppu_alias": "z2",
        "pairing": {"paired": True, "device_match": True,
                    "device_authenticated": True, "secret": "NEVER_OUTPUT"},
        "bootstrap": {"deployment": {"state": "idle"},
                      "runtime": {"state": "ready"}, "token": "NEVER_OUTPUT"},
    })
    with patch("plasma_cli.api.build_opener", return_value=opener):
        result = manager_deployment_status("http://127.0.0.1:18280", "z2")
    assert result["deployment_state"] == "idle"
    assert result["runtime_state"] == "ready"
    assert "NEVER_OUTPUT" not in json.dumps(result)
    assert opener.request.get_method() == "GET"
    assert opener.request.full_url.endswith("/api/registry/z2/bootstrap")


def test_deployment_multi_ppu_failure_is_isolated():
    def read(_url, alias, *, timeout):
        if alias == "blocked":
            raise FleetError("unreachable")
        return {"ppu_alias": alias, "status": "OBSERVED"}
    with patch("plasma_cli.main.manager_deployment_status", side_effect=read):
        result, complete = observe_deployments("http://localhost:18280", ["z2", "blocked"])
    assert not complete
    assert result["ppus"][0]["status"] == "OBSERVED"
    assert result["ppus"][1]["status"] == "NOT_VERIFIED"


def test_deployment_duplicate_alias_denied():
    with pytest.raises(FleetError, match="duplicate"):
        observe_deployments("http://localhost:18280", ["z2", "z2"])


@pytest.mark.parametrize("alias", ["", "..", ".", "../bad", "bad/name", "bad\\name", "  z2", "z2\n"])
def test_deployment_invalid_alias_denied_before_any_io(alias):
    with patch("plasma_cli.api.build_opener", side_effect=AssertionError("no I/O")):
        with pytest.raises(FleetError, match="invalid PPU alias"):
            manager_deployment_status("http://localhost:18280", alias)


def test_deploy_status_cli_uses_read_only_endpoint(capsys):
    with patch("plasma_cli.main.manager_deployment_status",
               return_value={"ppu_alias": "z2", "status": "OBSERVED"}) as read:
        status = main(["deploy", "status", "--ppu", "z2"])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["ppus"][0]["ppu_alias"] == "z2"
    read.assert_called_once()


@pytest.mark.parametrize("argv", [
    ["diagnose", "--target", "z2:0"],
    ["program", "receipt", "--batch-id", "a" * 32, "--target", "z2:1,1"],
])
def test_invalid_target_fails_before_any_manager_io(argv, capsys):
    with patch("plasma_cli.api.build_opener", side_effect=AssertionError("no I/O")):
        assert main(argv) == 2
    assert "Site IDs must be unique positive integers" in capsys.readouterr().err
