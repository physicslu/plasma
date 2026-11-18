"""Verified-result cache for load_engine / qualify_reference (Host-only).

A cached result is reused only while every source file keeps its stat
identity; any change re-runs the full verification, a failure is never
cached, and concurrent callers share one verification.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from .test_c3_rest_flash_cycle import make_engine, write_selection
from .test_opf_4a_openocd_reference import (
    IMAGE, PROFILE, engine, installed_bundle, reference,
)


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    reference._ENGINE_CACHE.clear()
    reference._REFERENCE_CACHE.clear()
    yield
    reference._ENGINE_CACHE.clear()
    reference._REFERENCE_CACHE.clear()


def _replace(path: Path, data: bytes) -> None:
    """Install new bytes as a new inode, as an installer would."""
    temporary = path.with_name(path.name + ".new")
    temporary.write_bytes(data)
    temporary.chmod(path.stat().st_mode & 0o7777)
    os.replace(temporary, path)


def _counting(monkeypatch, module, name):
    calls = []
    original = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def _engine(tmp_path):
    base = tmp_path / "openocd"
    data = make_engine(base, "0.12.0-aaaa-plasma-swd-111111111111", binary=b"OPENOCD-A")
    return write_selection(tmp_path / "engine.json", data), base, data


def test_engine_is_reused_until_its_binary_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    record, base, data = _engine(tmp_path)
    calls = _counting(monkeypatch, engine, "load_engine")
    first = reference.load_engine_verified(record, base=base, require_root=False)
    second = reference.load_engine_verified(record, base=base, require_root=False)
    assert first == second and len(calls) == 1
    _replace(Path(data["openocd_root"]) / "bin" / "openocd", b"OPENOCD-TAMPERED")
    with pytest.raises(engine.EngineNotReady, match="OPENOCD_SHA256_MISMATCH"):
        reference.load_engine_verified(record, base=base, require_root=False)
    assert len(calls) == 2


def test_engine_selection_change_is_verified_again(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    record, base, _ = _engine(tmp_path)
    other = make_engine(base, "0.12.0-bbbb-plasma-swd-222222222222", binary=b"OPENOCD-B")
    calls = _counting(monkeypatch, engine, "load_engine")
    first = reference.load_engine_verified(record, base=base, require_root=False)
    _replace(record, write_selection(tmp_path / "other.json", other).read_bytes())
    second = reference.load_engine_verified(record, base=base, require_root=False)
    assert len(calls) == 2
    assert str(second.openocd_root) == other["openocd_root"] != str(first.openocd_root)


def test_recently_changed_sources_are_never_reused(tmp_path, monkeypatch):
    # Default racy window: files created just now keep being re-verified.
    record, base, _ = _engine(tmp_path)
    calls = _counting(monkeypatch, engine, "load_engine")
    for _ in range(3):
        reference.load_engine_verified(record, base=base, require_root=False)
    assert len(calls) == 3


def test_unidentifiable_sources_are_never_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    record, base, _ = _engine(tmp_path)
    missing = tmp_path / "absent.json"
    calls = []
    real_load = engine.load_engine

    def fake_load(_record, *, base, require_root):
        calls.append(1)
        return real_load(record, base=base, require_root=require_root)

    monkeypatch.setattr(engine, "load_engine", fake_load)
    for _ in range(2):
        reference.load_engine_verified(missing, base=base, require_root=False)
    assert len(calls) == 2


def _qualify_kwargs(env, **changes):
    payload = {key: env[key] for key in (
        "product_root", "asset_set_sha256", "selection", "policy", "site_id",
        "target", "hardware", "engine_record", "engine_base", "require_root")}
    payload.update(image_size=len(IMAGE), operations=("erase", "program", "verify"))
    payload.update(changes)
    return payload


def test_qualification_is_reused_for_identical_inputs_and_copied(monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    with installed_bundle() as env:
        calls = _counting(monkeypatch, reference, "qualify_reference")
        first = reference.qualify_reference_cached(**_qualify_kwargs(env))
        first.profile["icpn"] = "MUTATED-BY-CALLER"
        second = reference.qualify_reference_cached(**_qualify_kwargs(env))
        assert len(calls) == 1
        assert second.profile["icpn"] == env["target"]
        assert second.route == first.route and second.engine == first.engine
        # Any input difference is a separate verification.
        reference.qualify_reference_cached(**_qualify_kwargs(env, site_id=1))
        reference.qualify_reference_cached(**_qualify_kwargs(env, image_size=16))
        hardware = {**env["hardware"], "worker_identity": {"session_id": "other"}}
        reference.qualify_reference_cached(**_qualify_kwargs(env, hardware=hardware))
        assert len(calls) == 4


def test_changed_staged_profile_is_verified_again_and_refused(monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    with installed_bundle() as env:
        calls = _counting(monkeypatch, reference, "qualify_reference")
        reference.qualify_reference_cached(**_qualify_kwargs(env))
        staged = env["product_root"] / "assets/staged" / env["asset_set_sha256"]
        profile = staged / f"payload/packages/{PROFILE}/{reference.PROFILE_FILE}"
        _replace(profile, profile.read_bytes() + b" ")
        with pytest.raises(Exception):
            reference.qualify_reference_cached(**_qualify_kwargs(env))
        assert len(calls) == 2


def test_changed_active_record_is_verified_again(monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    with installed_bundle() as env:
        calls = _counting(monkeypatch, reference, "qualify_reference")
        reference.qualify_reference_cached(**_qualify_kwargs(env))
        active = env["product_root"] / "assets/active.json"
        _replace(active, active.read_bytes())
        reference.qualify_reference_cached(**_qualify_kwargs(env))
        assert len(calls) == 2


def _source(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"v1")
    return source, (lambda: (reference._stat_identity(source),))


def test_concurrent_callers_share_one_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    cache = reference._VerifiedCache()
    _source_path, identity = _source(tmp_path)
    calls, results = [], []

    def compute():
        calls.append(1)
        time.sleep(0.2)
        return {"verified": True}

    threads = [threading.Thread(target=lambda: results.append(cache.get("k", identity, compute)))
               for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert sorted(hit for _, hit in results) == [False, True]
    assert all(value == {"verified": True} for value, _ in results)


def test_failures_and_sources_changed_during_verification_are_not_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_RACY_WINDOW_NS", 0)
    cache = reference._VerifiedCache()
    source, identity = _source(tmp_path)

    def failing():
        raise ValueError("DENIED")

    with pytest.raises(ValueError):
        cache.get("k", identity, failing)

    def changes_source():
        _replace(source, b"v2-longer")
        return "value"

    assert cache.get("k", identity, changes_source) == ("value", False)
    assert cache.get("k", identity, lambda: "again") == ("again", False)
    assert cache.get("k", identity, lambda: "unused") == ("again", True)
