"""C-3 OpenOCD engine install / select (Host-only; fake ARMv7 candidate artifacts)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_engine as engine  # noqa: E402
import ppu_site_worker_service as service  # noqa: E402

ELF_ARM = b"\x7fELF\x01\x01\x01" + b"\x00" * 11 + (40).to_bytes(2, "little")
SOURCE = "5088db4c9154ca833c6d558381074b33672e127a"


def candidate(tmp: Path, *, binary: bytes = ELF_ARM + b"openocd-A", admission=b"# admission\n",
              fields=True, corrupt_sum=False, evidence_extra=None, name=None) -> Path:
    files = {"openocd": binary, "plasma_swd_site_admission.py": admission,
             "tcl/target/stm32f1x.cfg": b"# cfg\n", "tcl/interface/x.cfg": b"# i\n",
             "PROVENANCE.txt": b"ci\n"}
    bin_sha = hashlib.sha256(binary).hexdigest()
    adm_sha = hashlib.sha256(admission).hexdigest()
    files["openocd.sha256"] = (f"{'0' * 64 if corrupt_sum else bin_sha}  openocd\n"
                               f"{adm_sha}  plasma_swd_site_admission.py\n").encode()
    evidence = {"schema": engine.CANDIDATE_SCHEMA, "openocd_source_sha": SOURCE,
                "plasma_source_sha": "f" * 40, "openocd_binary_sha256": bin_sha,
                "site_admission_script_sha256": adm_sha}
    if fields:
        evidence.update(adapter_driver="plasma_swd", driver_abi=5, adapter_khz=500,
                        openocd_version="0.12.0")
    evidence.update(evidence_extra or {})
    files["candidate-evidence.json"] = json.dumps(evidence).encode()
    tmp.mkdir(parents=True, exist_ok=True)
    art = tmp / (name or f"cand-{bin_sha[:8]}.tar.gz")
    with tarfile.open(art, "w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = 0o755 if path == "openocd" else 0o644
            tar.addfile(info, io.BytesIO(data))
    (art.parent / (art.name + ".sha256")).write_text(
        f"{hashlib.sha256(art.read_bytes()).hexdigest()}  {art.name}\n")
    return art


def install(art: Path, base: Path, **kw):
    return engine.install(art, base=base, require_root=False, **kw)


def test_install_select_two_engines_and_worker_uses_exactly_the_selected_one(tmp_path):
    base, record = tmp_path / "openocd", tmp_path / "engine.json"
    a = install(candidate(tmp_path / "a", binary=ELF_ARM + b"A"), base)
    b = install(candidate(tmp_path / "b", binary=ELF_ARM + b"B"), base)
    assert a["runtime_id"] != b["runtime_id"]
    assert a["runtime_id"].startswith("0.12.0-5088db4c9154-plasma-swd-")
    for chosen in (a, b, a):
        out = engine.select(chosen["runtime_id"], record=record, base=base, require_root=False)
        assert out["openocd_root"] == chosen["root"]
        adapter = service.default_adapter(record, base=base, require_root=False)
        assert str(adapter.openocd) == chosen["root"] + "/bin/openocd"
        assert adapter.adapter_khz == 500 and adapter.adapter_driver == "plasma_swd"
        assert adapter.engine_selection_sha256 == engine.load_engine(
            record, base=base, require_root=False).record_sha256
    # The Runtime picks its SWCLK independently of the driver default.
    engine.select(a["runtime_id"], record=record, base=base, require_root=False, adapter_khz=2000)
    assert service.default_adapter(record, base=base, require_root=False).adapter_khz == 2000
    with pytest.raises(engine.EngineNotReady, match="ADAPTER_KHZ_INVALID"):
        engine.select(a["runtime_id"], record=record, base=base, require_root=False, adapter_khz=0)
    listing = engine.list_engines(record=record, base=base, require_root=False)
    assert listing["selection"] == "READY"
    assert [e["selected"] for e in listing["engines"]].count(True) == 1



def test_admission_only_upgrade_gets_new_immutable_engine_id(tmp_path):
    # Same OpenOCD executable and source commit, but different Root/Site
    # admission logic must NOT alias an existing engine's immutable directory.
    base, record = tmp_path / "openocd", tmp_path / "engine.json"
    old = install(candidate(tmp_path / "old", admission=b"# old admission\\n"), base)
    fresh = install(candidate(tmp_path / "fresh", admission=b"# new admission\\n"), base)
    assert old["openocd_sha256"] == fresh["openocd_sha256"]
    assert old["admission_sha256"] != fresh["admission_sha256"]
    assert old["runtime_id"] != fresh["runtime_id"]
    assert fresh["runtime_id"].endswith(fresh["admission_sha256"][:12])
    assert (Path(old["root"]) / "libexec" / engine.ADMISSION_NAME).read_bytes() == b"# old admission\\n"
    assert (Path(fresh["root"]) / "libexec" / engine.ADMISSION_NAME).read_bytes() == b"# new admission\\n"
    # Do not switch the selected Engine merely because another version was installed.
    engine.select(old["runtime_id"], record=record, base=base, require_root=False)
    assert engine.load_engine(record, base=base, require_root=False).openocd_root == Path(old["root"])
    engine.select(fresh["runtime_id"], record=record, base=base, require_root=False)
    assert engine.load_engine(record, base=base, require_root=False).openocd_root == Path(fresh["root"])




def test_admission_only_install_preserves_selected_binary_tcl_and_clock(tmp_path):
    base, record = tmp_path / "engine", tmp_path / "selection.json"
    old = install(candidate(tmp_path / "old", binary=ELF_ARM + b"old-binary",
                            admission=b"# old\n"), base)
    engine.select(old["runtime_id"], record=record, base=base,
                  require_root=False, adapter_khz=2000)
    incoming = b"def current_site_admission():\n    return True\n"
    # The candidate intentionally has a DIFFERENT OpenOCD binary; only its
    # provenance-checked admission is eligible for import.
    art = candidate(tmp_path / "new", binary=ELF_ARM + b"other-binary",
                    admission=incoming)
    digest = hashlib.sha256(incoming).hexdigest()
    result = engine.install_selected_admission(
        art, expected_admission_sha256=digest,
        record=record, base=base, require_root=False)
    assert result["result"] == "ADMISSION_INSTALLED_NOT_SELECTED"
    assert result["openocd_sha256"] == old["openocd_sha256"]
    assert result["admission_sha256"] == digest
    assert result["selection_changed"] is False
    assert result["service_restarted"] is False
    assert result["fpga_reloaded"] is False
    assert result["flash"] == "NOT_RUN"
    assert (Path(result["runtime_id"]).name != old["runtime_id"])
    updated = base / result["runtime_id"]
    original = base / old["runtime_id"]
    assert (updated / "bin/openocd").read_bytes() == (original / "bin/openocd").read_bytes()
    assert (updated / "share/openocd/scripts/target/stm32f1x.cfg").read_bytes() == (
        original / "share/openocd/scripts/target/stm32f1x.cfg").read_bytes()
    assert (updated / "libexec" / engine.ADMISSION_NAME).read_bytes() == incoming
    assert (original / "libexec" / engine.ADMISSION_NAME).read_bytes() == b"# old\n"
    assert engine._manifest(updated)["adapter_khz"] == 2000
    # No automatic selection while installation is verified.
    assert engine.load_engine(record, base=base, require_root=False).openocd_root == original
    engine.select(result["runtime_id"], record=record, base=base, require_root=False)
    chosen = engine.load_engine(record, base=base, require_root=False)
    assert chosen.adapter_khz == 2000
    assert chosen.openocd_sha256 == old["openocd_sha256"]


def test_admission_only_install_denies_wrong_hash_and_legacy_api(tmp_path):
    base, record = tmp_path / "engine", tmp_path / "selection.json"
    old = install(candidate(tmp_path / "old", admission=b"# old\n"), base)
    engine.select(old["runtime_id"], record=record, base=base, require_root=False)
    art = candidate(tmp_path / "new", admission=b"DEVMEM_INDEPENDENT_IMAGES\n")
    with pytest.raises(engine.EngineNotReady, match="ADMISSION_CANDIDATE_SHA_MISMATCH"):
        engine.install_selected_admission(
            art, expected_admission_sha256="0" * 64,
            record=record, base=base, require_root=False)
    with pytest.raises(engine.EngineNotReady, match="ADMISSION_REMOVED_API_REFERENCE"):
        engine.install_selected_admission(
            art, expected_admission_sha256=hashlib.sha256(
                b"DEVMEM_INDEPENDENT_IMAGES\n").hexdigest(),
            record=record, base=base, require_root=False)
    assert [x.name for x in base.iterdir()] == [old["runtime_id"]]
    assert engine.load_engine(record, base=base, require_root=False).openocd_root.name == old["runtime_id"]


def test_install_is_idempotent_and_adopts_an_identical_side_by_side_install(tmp_path):
    base = tmp_path / "openocd"
    art = candidate(tmp_path / "a")
    first = install(art, base)
    assert first["adopted_existing"] is False
    assert install(art, base)["adopted_existing"] is True
    # A HIL-style install (same files + evidence/, no manifest) is adopted.
    root = Path(first["root"])
    (root / engine.MANIFEST_NAME).unlink()
    (root / "evidence").mkdir()
    (root / "evidence" / "run.log").write_text("hil\n")
    adopted = install(art, base)
    assert adopted["adopted_existing"] is True and (root / engine.MANIFEST_NAME).is_file()


def test_existing_install_with_different_bytes_is_refused(tmp_path):
    base = tmp_path / "openocd"
    first = install(candidate(tmp_path / "a"), base)
    (Path(first["root"]) / "share/openocd/scripts/target/stm32f1x.cfg").write_text("# changed\n")
    with pytest.raises(engine.EngineNotReady, match="EXISTING_INSTALL_DIFFERS"):
        install(candidate(tmp_path / "a2"), base)


@pytest.mark.parametrize("kw,code", [
    ({"corrupt_sum": True}, "ARTIFACT_INTERNAL_SHA256_MISMATCH"),
    ({"binary": b"#!/bin/sh\n"}, "OPENOCD_NOT_ELF32_ARM"),
    ({"evidence_extra": {"openocd_binary_sha256": "0" * 64}}, "ARTIFACT_EVIDENCE_MISMATCH"),
    ({"evidence_extra": {"driver_abi": 4}}, "DRIVER_ABI_UNSUPPORTED"),
    ({"evidence_extra": {"adapter_driver": "cmsis_dap"}}, "DRIVER_ABI_UNSUPPORTED"),
    ({"evidence_extra": {"adapter_khz": 0}}, "ADAPTER_KHZ_INVALID"),
    ({"fields": False}, "ARTIFACT_ENGINE_FIELDS_MISSING_DECLARE_THEM"),
])
def test_bad_artifacts_are_refused(tmp_path, kw, code):
    with pytest.raises(engine.EngineNotReady, match=code):
        install(candidate(tmp_path, **kw), tmp_path / "openocd")
    assert not any((tmp_path / "openocd").glob("0.*")) if (tmp_path / "openocd").exists() else True


def test_tampered_sidecar_and_unsafe_members_are_refused(tmp_path):
    art = candidate(tmp_path)
    (art.parent / (art.name + ".sha256")).write_text(f"{'1' * 64}  {art.name}\n")
    with pytest.raises(engine.EngineNotReady, match="ARTIFACT_SHA256_MISMATCH"):
        install(art, tmp_path / "openocd")
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    (tmp_path / "evil.tar.gz.sha256").write_text(
        f"{hashlib.sha256(evil.read_bytes()).hexdigest()}  evil.tar.gz\n")
    with pytest.raises(engine.EngineNotReady, match="ARTIFACT_MEMBER_UNSAFE"):
        install(evil, tmp_path / "openocd")


def test_older_artifact_needs_operator_declared_fields_recorded_as_such(tmp_path):
    out = install(candidate(tmp_path, fields=False), tmp_path / "openocd",
                  declared={"adapter_driver": "plasma_swd", "driver_abi": 5,
                            "adapter_khz": 500, "openocd_version": "0.12.0"})
    assert out["engine_fields_declared_by"] == "operator"


def test_select_refuses_missing_tampered_or_unmanifested_engines(tmp_path):
    base, record = tmp_path / "openocd", tmp_path / "engine.json"
    with pytest.raises(engine.EngineNotReady, match="ENGINE_NOT_INSTALLED"):
        engine.select("0.12.0-nope", record=record, base=base, require_root=False)
    good = install(candidate(tmp_path / "a"), base)
    (Path(good["root"]) / "bin" / "openocd").write_bytes(ELF_ARM + b"swapped")
    with pytest.raises(engine.EngineNotReady, match="OPENOCD_SHA256_MISMATCH"):
        engine.select(good["runtime_id"], record=record, base=base, require_root=False)
    bare = base / "0.12.0-hand-made"
    (bare / "bin").mkdir(parents=True)
    with pytest.raises(engine.EngineNotReady, match="ENGINE_NOT_INSTALLED_BY_TOOL"):
        engine.select(bare.name, record=record, base=base, require_root=False)
    with pytest.raises(engine.EngineNotReady, match="RUNTIME_ID_INVALID"):
        engine.select("../x", record=record, base=base, require_root=False)
    assert not record.exists()  # nothing was written by a refused select


def test_restart_happens_only_while_holding_the_runtime_gate(tmp_path):
    base, record = tmp_path / "openocd", tmp_path / "engine.json"
    out = install(candidate(tmp_path / "a"), base)
    events = []

    @contextlib.contextmanager
    def gate():
        events.append("gate")
        yield {}
        events.append("released")

    def run(argv, **kw):
        events.append(" ".join(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    engine.select(out["runtime_id"], record=record, base=base, require_root=False,
                  restart=True, hold_gate=gate, run=run)
    assert events == ["gate", "systemctl restart plasma-site-worker.service", "released"]

    @contextlib.contextmanager
    def busy():
        raise RuntimeError("ASSET_SET_QUIESCE_NOT_GRANTED")
        yield

    record.unlink()
    with pytest.raises(RuntimeError, match="QUIESCE_NOT_GRANTED"):
        engine.select(out["runtime_id"], record=record, base=base, require_root=False,
                      restart=True, hold_gate=busy, run=run)
    assert not record.exists()  # busy Runtime: the selection is not switched


def test_engine_tool_names_no_engine_version():
    source = (ROOT / "scripts" / "ppu_site_engine.py").read_text()
    assert "plasma-swd-" not in source and "5088db4c" not in source
    assert "/opt/plasma/python/" not in source
