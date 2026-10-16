"""Host-only LT02-05 HIL guards and real production-driver integration tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zlib

import pytest

from pl.hil.lt02 import native as n


def fake_manifest(tmp_path: Path):
    sha = "0123456789abcdef" * 2 + "12345678"
    bit = tmp_path / "candidate.bit"
    hwh = tmp_path / "candidate.hwh"
    firmware = tmp_path / "candidate.bin"
    recovery = tmp_path / "base.bin"
    original_hwh = tmp_path / "base.hwh"
    paths = (bit, hwh, firmware, recovery, original_hwh)
    for p, content in zip(paths, (b"BIT", b"HWH", b"BIN", b"BASE", b"BASE-HWH")):
        p.write_bytes(content)
    doc = dict(
        design_variant="lt02_axi_scratchpad_internal_dpidr_fixture",
        fpga_part="xc7z020clg400-1",
        board_part="tul.com.tw:pynq-z2:part0:1.0",
        source_git_sha=sha,
        build_id=sha[:32],
        external_pl_io=False, hardware_runtime_ready=False,
        physical_programming_qualified=False,
        lt02_abi_version=1, lt02_scratchpad_bytes=2048,
        lt02_reference_site_id=1,
        bitstream_sha256=n.digest(bit),
        hwh_sha256=n.digest(hwh),
        axi_address_map={name: dict(
            base_address=f"0x{base:08X}", segment_size_bytes=4096)
            for name, base in n.AXI_BASES.items()},
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(doc))
    return manifest, paths, doc


def test_exact_five_apertures_and_real_manifest_contract(tmp_path, monkeypatch):
    manifest, paths, doc = fake_manifest(tmp_path)
    monkeypatch.setattr(n.old, "RECOVERY_BIN_SHA256", n.digest(paths[3]))
    monkeypatch.setattr(n.old, "RECOVERY_HWH_SHA256", n.digest(paths[4]))
    fingerprint = n.digest(manifest)
    proof = n.verify_artifacts(manifest, *paths, fingerprint)
    assert proof["source_git_sha"] == doc["source_git_sha"]
    assert proof["build_id"] == doc["build_id"]
    assert proof["manifest_sha256"] == fingerprint


@pytest.mark.parametrize("field,bad", [
    ("design_variant", "swd03_axi_internal_dpidr_fixture"),
    ("fpga_part", "xc7z010clg400-1"),
    ("external_pl_io", True),
    ("hardware_runtime_ready", True),
    ("lt02_abi_version", 2),
    ("lt02_scratchpad_bytes", 1024),
    ("lt02_reference_site_id", 0),
    ("build_id", "0" * 32),
])
def test_manifest_fails_closed(tmp_path, monkeypatch, field, bad):
    manifest, paths, doc = fake_manifest(tmp_path)
    monkeypatch.setattr(n.old, "RECOVERY_BIN_SHA256", n.digest(paths[3]))
    monkeypatch.setattr(n.old, "RECOVERY_HWH_SHA256", n.digest(paths[4]))
    doc[field] = bad
    manifest.write_text(json.dumps(doc))
    with pytest.raises(n.LT02SafetyError):
        n.verify_artifacts(manifest, *paths, n.digest(manifest))


@pytest.mark.parametrize("change", ["missing", "extra", "addr", "size"])
def test_hardware_map_requires_five_exact_pages(tmp_path, monkeypatch, change):
    manifest, paths, doc = fake_manifest(tmp_path)
    monkeypatch.setattr(n.old, "RECOVERY_BIN_SHA256", n.digest(paths[3]))
    monkeypatch.setattr(n.old, "RECOVERY_HWH_SHA256", n.digest(paths[4]))
    mapping = doc["axi_address_map"]
    if change == "missing":
        del mapping["lt02_0"]
    elif change == "extra":
        mapping["wrong"] = mapping["lt02_0"]
    elif change == "addr":
        mapping["lt02_0"]["base_address"] = "0x40005000"
    else:
        mapping["lt02_0"]["segment_size_bytes"] = 8192
    manifest.write_text(json.dumps(doc))
    with pytest.raises(n.LT02SafetyError):
        n.verify_artifacts(manifest, *paths, n.digest(manifest))


def test_candidate_bit_and_hwh_must_match_manifest(tmp_path, monkeypatch):
    manifest, paths, _ = fake_manifest(tmp_path)
    monkeypatch.setattr(n.old, "RECOVERY_BIN_SHA256", n.digest(paths[3]))
    monkeypatch.setattr(n.old, "RECOVERY_HWH_SHA256", n.digest(paths[4]))
    paths[1].write_bytes(b"HWH changed")
    with pytest.raises(n.LT02SafetyError, match="HWH"):
        n.verify_artifacts(manifest, *paths, n.digest(manifest))


def test_wrong_recovery_image_blocks_even_if_candidate_correct(tmp_path):
    manifest, paths, _ = fake_manifest(tmp_path)
    with pytest.raises(n.LT02SafetyError, match="recovery"):
        n.verify_artifacts(manifest, *paths, n.digest(manifest))


def test_load_receipt_must_match_current_boot_load_and_candidate():
    artifact = dict(candidate_bin_sha256="a" * 64,
                    manifest_sha256="b" * 64, build_id="c" * 32)
    good = dict(boot_id="boot-current",
                load_line="[99] fpga_manager fpga0: writing lt02.bin to manager",
                candidate_bin_sha256=artifact["candidate_bin_sha256"],
                manifest_sha256=artifact["manifest_sha256"],
                build_id=artifact["build_id"],
                axi_address_map=dict(n.AXI_BASES),
                site_id=1, external_pl_io=False)
    n.verify_receipt(good, boot_id=good["boot_id"],
                     last_load_line=good["load_line"], artifact=artifact)
    for field in list(good):
        changed = dict(good)
        changed[field] = None
        with pytest.raises(n.LT02SafetyError, match="receipt"):
            n.verify_receipt(changed, boot_id=good["boot_id"],
                             last_load_line=good["load_line"],
                             artifact=artifact)


def test_hil_default_inert_even_with_nonexistent_files(capsys, tmp_path):
    argv = []
    for name in ("manifest", "bit", "hwh", "candidate-bin",
                 "recovery-bin", "recovery-hwh", "receipt", "output"):
        argv.extend(["--" + name, str(tmp_path / name)])
    argv.extend(["--expected-manifest-sha256", "0" * 64])
    assert n.main(argv) == 2
    assert "inert" in capsys.readouterr().err
    assert n.main(argv + ["--execute-live"]) == 2
    assert n.main(argv + ["--ack-unrecoverable-axi-stall-risk"]) == 2
    assert not (tmp_path / "output").exists()


def test_wrong_platform_is_rejected_before_any_live_file_or_mmio(monkeypatch, tmp_path):
    argv = []
    for name in ("manifest", "bit", "hwh", "candidate-bin",
                 "recovery-bin", "recovery-hwh", "receipt", "output"):
        argv.extend(["--" + name, str(tmp_path / name)])
    argv += ["--expected-manifest-sha256", "0" * 64,
             "--execute-live", "--ack-unrecoverable-axi-stall-risk"]
    def reject():
        raise n.old.SafetyError("wrong platform")
    monkeypatch.setattr(n, "check_runtime", reject)
    monkeypatch.setattr(n, "verify_artifacts",
                        lambda *a: (_ for _ in ()).throw(
                            AssertionError("MUST NOT verify/open live devices")))
    assert n.main(argv) == 2
    assert not (tmp_path / "output").exists()


class FakeMMIO:
    """Host-only word-port fixture; PL RTL is tested separately in Cocotb."""

    def __init__(self, sha):
        self.identity = n.expected_identity(sha)
        self.words = {}
        self.writes = 0
        self.reads = 0
        self.claims = []

    def read32(self, address):
        if address in self.identity:
            return self.identity[address]
        offset = address - n.LT02
        if offset in {0, 4, 8, 12, 20, 24, 28}:
            return {
                0: 0x4C543032, 4: 0x10000, 8: 1, 12: 2048,
                20: 1, 24: self.writes, 28: self.reads,
            }[offset]
        assert 0x100 <= offset <= 0x8FC and offset % 4 == 0
        self.reads += 1
        return self.words.get(offset, 0)

    def write32(self, address, value):
        offset = address - n.LT02
        assert 0x100 <= offset <= 0x8FC and offset % 4 == 0
        self.writes += 1
        self.words[offset] = value

    def claim_site(self, site_id, base):
        assert (site_id, base) == (1, n.LT02)
        self.claims.append((site_id, base))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_production_driver_hil_case_matrix_injected_host():
    source = "0123456789abcdef" * 2 + "12345678"
    bus = FakeMMIO(source)
    cases = n.run_cases(bus, source)
    assert [v["bytes"] for v in cases] == list(n.LENGTHS)
    assert all(v["write_words"] == v["read_words"] and v["crc32"]
               == f"{zlib.crc32(n.case_payload(v['bytes'], i)):08x}"
               for i, v in enumerate(cases))
    assert [v["chunks"] for v in cases if v["bytes"] == 2049] == [2]
    assert bus.claims == [(1, n.LT02)]


def test_wrong_candidate_build_id_stops_before_data_writes():
    source = "0123456789abcdef" * 2 + "12345678"
    bus = FakeMMIO(source)
    with pytest.raises(n.LT02SafetyError, match="Identity"):
        n.run_cases(bus, "1" * 40)
    assert bus.writes == 0


def test_wrong_lt02_abi_stops_before_data_writes():
    source = "0123456789abcdef" * 2 + "12345678"
    bus = FakeMMIO(source)
    read = bus.read32
    bus.read32 = lambda addr: 0 if addr == n.LT02 + 4 else read(addr)
    with pytest.raises(n.LoopTestError):
        n.run_cases(bus, source)
    assert bus.writes == 0


@pytest.fixture
def trees(tmp_path):
    sys, proc = tmp_path / "sys", tmp_path / "proc"
    (sys / "bus/platform/devices").mkdir(parents=True)
    (sys / "class/uio").mkdir(parents=True)
    (proc / "111/fd").mkdir(parents=True)
    (proc / "111/maps").write_text("")
    return sys, proc


def test_ownership_checks_new_fifth_aperture(trees):
    sys, proc = trees
    n.check_ownership(sysroot=sys, procroot=proc)
    (proc / "111/maps").write_text(
        "1000-2000 rw-s 40004000 00:01 1 /dev/mem\n")
    with pytest.raises(n.LT02SafetyError, match="retained"):
        n.check_ownership(sysroot=sys, procroot=proc)


def test_fifth_aperture_uio_driver_conflict(trees):
    sys, proc = trees
    mapping = sys / "class/uio/uio7/maps/map0"
    mapping.mkdir(parents=True)
    (mapping / "addr").write_text("0x40004000")
    (mapping / "size").write_text("0x1000")
    (sys / "class/uio/uio7/device/driver").mkdir(parents=True)
    with pytest.raises(n.LT02SafetyError, match="kernel UIO"):
        n.check_ownership(sysroot=sys, procroot=proc)


def test_unrelated_retained_uio_is_excluded_only_when_identified(trees):
    sys, proc = trees
    mapping = sys / "class/uio/uio7/maps/map0"
    mapping.mkdir(parents=True)
    (mapping / "addr").write_text("0x43c00000")
    (mapping / "size").write_text("0x1000")
    (proc / "111/maps").write_text(
        "1000-2000 rw-s 00000000 00:01 1 /dev/uio7\n")
    n.check_ownership(sysroot=sys, procroot=proc)


def test_fclk_enabled_guard():
    assert n.check_fclk_enabled("fclk0 1 1 100000000")
    assert not n.check_fclk_enabled("fclk0 0 0 100000000")
    assert not n.check_fclk_enabled("missing 1 1 100000000")
