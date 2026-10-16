"""Default-inert MS01 Z2 HIL CLI tests, no FPGA, /dev/mem or SSH."""
from __future__ import annotations

from pathlib import Path

import pytest

from pl.hil.ms01 import native
from pl.hil.ms01.benchmark import MODES


def args(tmp_path: Path) -> list[str]:
    paths = {name: tmp_path / name.replace("-", "_")
             for name in ("manifest", "bit", "hwh", "candidate-bin",
                          "recovery-bin", "recovery-hwh", "receipt", "output")}
    command = []
    for name, path in paths.items():
        command += ["--" + name, str(path)]
    return command + [
        "--expected-manifest-sha256", "0" * 64,
        "--expected-candidate-bin-sha256", "0" * 64,
    ]


def test_dual_site_identity_and_reference_map():
    assert native.SITE_BASES == {1: 0x40004000, 2: 0x40005000}
    assert set(native.MAP) == {"identity_0", "control_0", "swd_0",
                               "transaction_0", "lt02_0", "lt02_1"}


def test_cli_fails_closed_without_explicit_mode(monkeypatch, tmp_path):
    def forbid(**kwargs):
        raise AssertionError("No artifacts or hardware should be touched")
    monkeypatch.setattr(native, "verify_artifacts", forbid)
    assert native.main(args(tmp_path)) == 2
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("extras", [
    ["--record-loaded-image", "--execute-live"],
    ["--record-loaded-image", "--ack-unrecoverable-axi-stall-risk"],
    ["--execute-live"],
    ["--execute-live", "--ack-unrecoverable-axi-stall-risk", "--iterations", "0"],
    ["--execute-live", "--ack-unrecoverable-axi-stall-risk", "--payload-sizes", "0"],
])
def test_unsafe_modes_refused_before_artifacts(monkeypatch, tmp_path, extras):
    def forbid(**kwargs):
        raise AssertionError("No artifacts or hardware should be touched")
    monkeypatch.setattr(native, "verify_artifacts", forbid)
    assert native.main(args(tmp_path) + extras) == 2


def test_no_direct_process_without_separate_owner_design():
    assert "process-direct" not in MODES
    assert MODES == ("thread", "process-ipc")
