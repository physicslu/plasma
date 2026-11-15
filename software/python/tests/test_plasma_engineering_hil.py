from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/plasma_engineering_hil.py"
spec = importlib.util.spec_from_file_location("plasma_engineering_hil", SCRIPT)
assert spec is not None and spec.loader is not None
hil = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hil)

S = "c" * 64
PLAN_ID = "a" * 32
START_ID = "b" * 32
BATCH_ID = "d" * 32
META = hil.IMAGES["v0.1"]
IMAGE = {"version": "v0.1", "sha256": META["sha256"],
         "size": META["size"], "image_base64": "fake-encoded-image"}


def make_batch(image=IMAGE) -> dict:
    receipt = {
        "safe_off": True,
        "readback_sha256": image["sha256"],
        "expected_image_sha256": image["sha256"],
        "observed_image_sha256": image["sha256"],
        "bytes_verified": image["size"],
        "expected_image_size": image["size"],
        "observed_image_size": image["size"],
        "expected_resource_set_sha256": S,
        "observed_resource_set_sha256": S,
        "resource_reuse": True,
        "observed_operations": hil.OPERATIONS,
        "attempts": 1,
        "expected_job_binding_sha256": "e" * 64,
        "observed_job_binding_sha256": "e" * 64,
        "expected_steps": {"verify": {"readback_sha256": image["sha256"]}},
        "observed_steps": {"verify": {"readback_sha256": image["sha256"]}},
        "job_id": "job-fixture",
    }
    return {
        "batch_id": BATCH_ID, "outcome": "PASS",
        "execution_status": "COMPLETED",
        "counts": {"pass": 1, "sites": 1},
        "units": [{"ppu_alias": "z2", "site_id": 2, "outcome": "PASS",
                   "attempts": [{"outcome": "PASS", "safe_off": True}]}],
        "current_run": {"outcome": "PASS", "receipt": receipt, "job_submission_count": 1},
    }


class StubManager:
    def __init__(self, activation: bool = False, fail_batch: bool = False):
        self.calls = []
        self.activation = activation
        self.fail_batch = fail_batch

    def call(self, method: str, route: str, body=None):
        self.calls.append((method, route, body))
        if route.endswith("/programming/plans"):
            return {"ok": True, "plan": {
                "plan_id": PLAN_ID, "activation_required": self.activation,
                "resource": {"reuse": not self.activation,
                             "resource_set_sha256": S},
                "fpga_load": False,
                "image_asset": {"sha256": IMAGE["sha256"], "size": IMAGE["size"]},
            }}
        if route.endswith("/void"):
            return {"ok": True, "reconciliation": {"state": "NOT_ACCEPTED"}}
        if route == "/api/programming/starts":
            return {"ok": True, "start": {"start_id": START_ID}}
        if route == "/api/programming/batches":
            if self.fail_batch:
                raise hil.HILFailure("POST outcome unknown")
            return {"ok": True, "batch": make_batch()}
        raise AssertionError(route)


def test_smoke_and_burnin_separate_sequences() -> None:
    assert hil.sequence("smoke", 1) == ["v0.1", "v0.2", "v0.1"]
    assert hil.sequence("burn-in", 2) == ["v0.1", "v0.2"] * 2
    with pytest.raises(hil.HILFailure):
        hil.sequence("smoke", 2)


def test_live_hil_is_swpc_linux_only() -> None:
    if hil.sys.platform == "linux":
        hil.require_swpc_hostname("SWPC")
    with pytest.raises(hil.HILFailure, match="restricted to the SWPC"):
        hil.require_swpc_hostname("untrusted-runner")


def test_external_manager_rejected() -> None:
    with pytest.raises(hil.HILFailure, match="SWPC loopback"):
        hil.require_loopback("http://192.168.2.99:18280")
    assert hil.require_loopback("http://127.0.0.1:18280/") == "http://127.0.0.1:18280"


def test_wrong_image_sha_rejected(tmp_path: Path) -> None:
    image = tmp_path / "wrong.bin"
    image.write_bytes(b"this is not the pinned firmware")
    with pytest.raises(hil.HILFailure, match="image size/SHA256"):
        hil.image_spec(image, "v0.1")


def test_reuse_preflight_refuses_activation_before_any_batch() -> None:
    manager = StubManager(activation=True)
    with pytest.raises(hil.HILFailure, match="RESOURCE_REUSE_NOT_PROVEN"):
        hil.one_attempt(manager, "z2", 2, IMAGE, 10, 1)
    assert [x[1] for x in manager.calls] == [
        "/api/registry/z2/bootstrap/programming/plans",
        f"/api/programming/starts/{PLAN_ID}/void",
    ]


def test_manager_batch_e2e_validates_receipt_without_real_hardware() -> None:
    manager = StubManager()
    result, raw = hil.one_attempt(manager, "z2", 2, IMAGE, 10, 1)
    assert result["readback_sha256"] == IMAGE["sha256"]
    assert result["safe_off"] is True
    assert raw["start_id"] == START_ID
    assert [x[1] for x in manager.calls] == [
        "/api/registry/z2/bootstrap/programming/plans",
        f"/api/programming/starts/{PLAN_ID}/void",
        "/api/programming/starts",
        "/api/programming/batches",
    ]
    body = manager.calls[-1][2]
    assert body["repeat"] == 1 and body["retry_limit"] == 0
    assert body["targets"] == [{"ppu_alias": "z2", "site_ids": [2]}]


def test_no_resubmit_on_unknown_batch_post() -> None:
    manager = StubManager(fail_batch=True)
    with pytest.raises(hil.HILFailure, match="start_id="):
        hil.one_attempt(manager, "z2", 2, IMAGE, 10, 1)
    assert [x[1] for x in manager.calls].count("/api/programming/batches") == 1
    assert manager.last_start_id == START_ID


@pytest.mark.parametrize("bad_field,bad_value", [
    ("safe_off", False), ("readback_sha256", "0" * 64),
    ("resource_reuse", False), ("bytes_verified", 0),
])
def test_receipt_negative_cases(bad_field, bad_value) -> None:
    batch = make_batch()
    batch["current_run"]["receipt"][bad_field] = bad_value
    with pytest.raises(hil.HILFailure, match="Receipt"):
        hil.validate_receipt(batch, "z2", 2, IMAGE, S)


def test_no_auto_deploy_or_legacy_programmer() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    router = (ROOT / "scripts/plasmactl").read_text(encoding="utf-8")
    assert '  hil)' in router and 'plasma_engineering_hil.py' in router
    assert "plasma_wordport_program.py" not in source
    assert "plasmactl deploy" not in source
    assert "--execute" in source
