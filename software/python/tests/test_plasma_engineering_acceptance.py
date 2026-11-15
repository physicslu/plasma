from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/plasma_engineering_acceptance.py"
spec = importlib.util.spec_from_file_location("plasma_engineering_acceptance", SCRIPT)
assert spec is not None and spec.loader is not None
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)
SHA = "a" * 40


def opts(tmp_path: Path, *, execute=True) -> argparse.Namespace:
    return argparse.Namespace(
        profile="bluepill-ab", site=2, ppu_alias="z2",
        image_v01=Path("/fixture/v01.bin"), image_v02=Path("/fixture/v02.bin"),
        port="/dev/serial/by-id/test-device", expected_source_sha=SHA,
        execute=execute, deploy_timeout=600, hil_timeout=2700,
        output=tmp_path / "evidence",
    )


class FakeCommands:
    def __init__(self, *, dirty=False, deployed_sha=SHA, fail_stage=None):
        self.calls = []
        self.dirty = dirty
        self.deployed_sha = deployed_sha
        self.fail_stage = fail_stage

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        if "rev-parse" in argv:
            return SHA + "\n"
        if "--porcelain" in argv:
            return " M unmanaged-file\n" if self.dirty else ""
        tag = argv[1:3]
        if self.fail_stage and tag == self.fail_stage:
            raise acceptance.AcceptanceBlocked("RECEIPT_UNKNOWN_DO_NOT_RETRY")
        if tag == ["status", "local-control-station"]:
            return f"Profile: local-control-station\nGit SHA: {self.deployed_sha}\n"
        return "PASS"


def test_plan_only_never_deploys_or_touches_hardware(tmp_path: Path) -> None:
    run_cmd = FakeCommands()
    assert acceptance.run(opts(tmp_path, execute=False), run_cmd) == 0
    assert len(run_cmd.calls) == 3
    assert run_cmd.calls[-1][1:3] == ["hil", "programming"]
    assert "--execute" not in run_cmd.calls[-1]
    assert not (tmp_path / "evidence").exists()


def test_live_order_pinned_sha_and_separate_stages(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    fake = FakeCommands()
    assert acceptance.run(opts(tmp_path), fake) == 0
    commands = [x[1:3] for x in fake.calls[2:]]
    assert commands == [
        ["hil", "programming"], ["deploy", "local-control-station"],
        ["status", "local-control-station"], ["verify", "local-control-station"],
        ["hil", "programming"],
    ]
    assert "--execute" not in fake.calls[2]
    assert "--execute" in fake.calls[-1]
    report_file = next((tmp_path / "evidence").glob("*/summary.json"))
    report = json.loads(report_file.read_text())
    assert report["result"] == "PASS"
    assert report["source_sha"] == SHA
    assert len(report["stages"]) == 5


def test_live_rejects_dirty_source_before_hardware(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    fake = FakeCommands(dirty=True)
    with pytest.raises(acceptance.AcceptanceBlocked, match="NOT_CLEAN"):
        acceptance.run(opts(tmp_path), fake)
    assert len(fake.calls) == 2


def test_live_rejects_missing_owner_pinned_sha(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    args = opts(tmp_path)
    args.expected_source_sha = ""
    fake = FakeCommands()
    with pytest.raises(acceptance.AcceptanceBlocked, match="EXACT_SOURCE_SHA"):
        acceptance.run(args, fake)
    assert len(fake.calls) == 2


def test_live_rejects_wrong_source_sha_before_deploy(tmp_path: Path) -> None:
    args = opts(tmp_path)
    args.expected_source_sha = "b" * 40
    fake = FakeCommands()
    with pytest.raises(acceptance.AcceptanceBlocked, match="SOURCE_SHA_NOT_APPROVED"):
        acceptance.run(args, fake)
    assert len(fake.calls) == 2


def test_live_blocks_wrong_release_identity_before_hil(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    fake = FakeCommands(deployed_sha="f" * 40)
    assert acceptance.run(opts(tmp_path), fake) == 2
    commands = [x[1:3] for x in fake.calls]
    assert commands.count(["deploy", "local-control-station"]) == 1
    assert commands.count(["hil", "programming"]) == 1
    report_file = next((tmp_path / "evidence").glob("*/summary.json"))
    report = json.loads(report_file.read_text())
    assert report["result"] == "BLOCKED"
    assert report["reason"] == "DEPLOYED_RELEASE_SHA_MISMATCH"


@pytest.mark.parametrize("stage", [
    ["hil", "programming"], ["deploy", "local-control-station"],
    ["verify", "local-control-station"],
])
def test_no_hil_or_deploy_retry_after_stage_failure(
    tmp_path: Path, monkeypatch, stage,
) -> None:
    monkeypatch.setattr(acceptance.socket, "gethostname", lambda: "SWPC")
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    fake = FakeCommands(fail_stage=stage)
    assert acceptance.run(opts(tmp_path), fake) == 2
    operations = [x[1:3] for x in fake.calls]
    assert operations.count(["deploy", "local-control-station"]) <= 1
    assert operations.count(["hil", "programming"]) <= 2
    report_file = next((tmp_path / "evidence").glob("*/summary.json"))
    assert json.loads(report_file.read_text())["result"] == "BLOCKED"


def test_real_runner_guards_are_not_bypassed_by_composition() -> None:
    router = (ROOT / "scripts/plasmactl").read_text()
    source = SCRIPT.read_text()
    assert '  acceptance)' in router
    assert '"--execute"' in source
    assert "expected_source_sha" in source
    assert '["deploy", "local-control-station"]' not in source  # runs the canonical CLI
    assert 'plasma_engineering_hil.py' not in source  # routes through plasmactl HIL
