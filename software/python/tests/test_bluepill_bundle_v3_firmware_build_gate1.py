"""Host-only validation of reproducible, exact-source Blue Pill Bundle v3."""

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import ppu_unified_deployment  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "bluepill_bundle_fixture_builder",
    ROOT / "scripts/bluepill_bundle_v3_firmware_build.py",
)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

V01 = ROOT / "docs/evidence/bluepill-z2-flash-2026-10-27/firmware/plasma-blue-pill-cdc.bin"
EXPECTED_V01_BUNDLE_SHA = "71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a"


def test_v01_fixture_exact_source_reproduces_same_zip(tmp_path):
    assert V01.is_file()
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    first = builder.build("v0.1", V01, a)
    other = builder.build("v0.1", V01, b)
    assert first["status"] == "HOST_ONLY_VERIFIED_NOT_DEPLOYED"
    assert first == other
    assert a.read_bytes() == b.read_bytes()
    assert first["archive_sha256"] == EXPECTED_V01_BUNDLE_SHA
    parsed = ppu_unified_deployment.verify_host_only_bundle(
        a, expected_sha256=first["archive_sha256"], target_profile=builder.TARGET)
    assert len(parsed.packages) == 3
    assert {p.kind for p in parsed.packages} == {
        "platform-provider", "programming-profile", "firmware-asset"}
    with zipfile.ZipFile(a) as z:
        assert z.read("manifest.json").count(b'"actions":["install","verify"]') == 1


@pytest.mark.parametrize("case", ["wrong_bytes", "wrong_variant", "symlink", "output_exists"])
def test_bad_fixture_input_never_writes_archive(tmp_path, case):
    source = V01
    variant = "v0.1"
    output = tmp_path / "bundle.zip"
    if case == "wrong_bytes":
        source = tmp_path / "mutated.bin"
        data = bytearray(V01.read_bytes())
        data[0] ^= 1
        source.write_bytes(data)
    elif case == "wrong_variant":
        variant = "v0.2"
    elif case == "symlink":
        source = tmp_path / "link.bin"
        source.symlink_to(V01)
    else:
        output.write_bytes(b"existing")
    with pytest.raises(builder.FixtureDenied):
        builder.build(variant, source, output)
    if case == "output_exists":
        assert output.read_bytes() == b"existing"
    else:
        assert not output.exists()
