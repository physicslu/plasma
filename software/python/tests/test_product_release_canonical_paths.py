from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "product-release.py"
spec = importlib.util.spec_from_file_location("product_release_canonical_paths", SCRIPT)
assert spec is not None and spec.loader is not None
product_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = product_release
spec.loader.exec_module(product_release)


def test_verifier_rejects_dot_segment_archive_alias_before_extraction(tmp_path: Path) -> None:
    artifact = tmp_path / "dot-segment.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("plasma-release/./runtime/escape.txt", "escape")
    product_release._write_archive_sidecar(artifact)

    with pytest.raises(product_release.ReleaseError, match="canonical POSIX form"):
        product_release.verify_release(artifact)


def test_canonical_relative_path_round_trips_without_normalization() -> None:
    value = "plasma-release/runtime/bin/plasma-runtime.txt"
    assert product_release._validate_relative_posix_path(value).as_posix() == value
