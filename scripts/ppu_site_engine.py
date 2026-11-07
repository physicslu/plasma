#!/usr/bin/env python3
"""C-3 OpenOCD engine: install, select and verify (root on Z2; no hardware).

The Site Worker never names an OpenOCD version. It runs the engine recorded
in the root-owned selection record ``/etc/plasma/site-worker-engine.json``
(schema ``plasma.ppu.site-worker-engine.v1``). This module is the ONE owner
of that record:

``install ARTIFACT [--sidecar S]``
    Verify a CI ``plasma-openocd5088-armv7-candidate.tar.gz`` (detached
    SHA-256 sidecar, internal ``openocd.sha256``, ELF32 ARM, safe members)
    and install it immutably under
    ``/opt/plasma/programming-engines/openocd/<runtime_id>/`` with an engine
    manifest ``plasma-engine.json`` (driver, ABI, qualified adapter speed,
    digests). An identical existing install (e.g. a side-by-side HIL install)
    is verified byte-for-byte and adopted; a different one is refused.
``select RUNTIME_ID [--adapter-khz N] [--restart]``
    Re-verify that installed engine and atomically write the selection
    record (SWCLK = ``--adapter-khz`` or the engine's driver default). ``--restart`` restarts ``plasma-site-worker.service`` while
    holding the Runtime's Job-admission gate (no active Job); without it the
    new selection takes effect on the next Worker start.
``list``
    Installed engines (with/without manifest) and the current selection.

No path, version or build ID of any engine is written in source here.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

ENGINE_SELECTION = Path("/etc/plasma/site-worker-engine.json")
ENGINE_BASE = Path("/opt/plasma/programming-engines/openocd")
ENGINE_SCHEMA = "plasma.ppu.site-worker-engine.v1"
MANIFEST_NAME = "plasma-engine.json"
MANIFEST_SCHEMA = "plasma.ppu.openocd-engine.v1"
CANDIDATE_SCHEMA = "plasma.openocd.armv7.candidate-evidence.v1"
SUPPORTED_DRIVER_ABI = {"plasma_swd": frozenset({5})}
ADMISSION_NAME = "plasma_swd_site_admission.py"
RUNTIME_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,127}\Z")
MAX_MEMBERS = 20000
MAX_BYTES = 512 * 1024 * 1024
WORKER_UNIT = "plasma-site-worker.service"


class EngineNotReady(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EngineSelection:
    openocd_root: Path
    openocd_sha256: str
    admission_sha256: str
    adapter_driver: str
    driver_abi: int
    adapter_khz: int
    record_sha256: str


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise EngineNotReady(code)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _trusted_file(path: Path, *, require_root: bool) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise EngineNotReady("MISSING:" + path.name) from None
    except OSError:
        raise EngineNotReady("UNREADABLE:" + path.name) from None
    _need(stat.S_ISREG(info.st_mode), "NOT_REGULAR_FILE:" + path.name)
    _need(info.st_mode & 0o022 == 0, "WRITABLE_BY_OTHERS:" + path.name)
    if require_root:
        _need(info.st_uid == 0, "NOT_ROOT_OWNED:" + path.name)
    return info


def _engine_fields(data: Any, code: str) -> tuple[str, int, int]:
    _need(isinstance(data, dict), code)
    driver, abi, khz = data.get("adapter_driver"), data.get("driver_abi"), data.get("adapter_khz")
    _need(type(driver) is str and driver in SUPPORTED_DRIVER_ABI
          and type(abi) is int and abi in SUPPORTED_DRIVER_ABI[driver],
          "DRIVER_ABI_UNSUPPORTED")
    _need(type(khz) is int and 0 < khz <= 100_000, "ADAPTER_KHZ_INVALID")
    return driver, abi, khz


def verify_installed(root: Path, *, openocd_sha256: str, admission_sha256: str,
                     require_root: bool = True) -> None:
    binary = root / "bin" / "openocd"
    admission = root / "libexec" / ADMISSION_NAME
    _trusted_file(binary, require_root=require_root)
    _trusted_file(admission, require_root=require_root)
    _need(_sha256(binary) == openocd_sha256, "OPENOCD_SHA256_MISMATCH")
    _need(_sha256(admission) == admission_sha256, "ADMISSION_SHA256_MISMATCH")
    _need((root / "share" / "openocd" / "scripts").is_dir(), "SCRIPTS_ROOT_MISSING")


def load_engine(record: Path = ENGINE_SELECTION, *, base: Path = ENGINE_BASE,
                require_root: bool = True) -> EngineSelection:
    """Resolve and verify the selected OpenOCD engine (raises EngineNotReady;
    never guesses an install from directory names, never falls back)."""
    _trusted_file(record, require_root=require_root)
    try:
        raw = record.read_bytes()
        data: Any = json.loads(raw)
    except (OSError, ValueError):
        raise EngineNotReady("SELECTION_UNREADABLE") from None
    _need(isinstance(data, dict) and set(data) == {
        "schema", "openocd_root", "openocd_sha256", "admission_sha256",
        "adapter_driver", "driver_abi", "adapter_khz"}, "SELECTION_FIELDS_INVALID")
    _need(data["schema"] == ENGINE_SCHEMA, "SELECTION_SCHEMA_UNSUPPORTED")
    root_raw = data["openocd_root"]
    _need(type(root_raw) is str and Path(root_raw).is_absolute()
          and ".." not in Path(root_raw).parts, "SELECTION_ROOT_INVALID")
    root = Path(root_raw)
    _need(root.parent == base and not root.is_symlink() and root.is_dir(),
          "SELECTION_ROOT_NOT_INSTALLED")
    for field in ("openocd_sha256", "admission_sha256"):
        _need(type(data[field]) is str and re.fullmatch(r"[0-9a-f]{64}", data[field]) is not None,
              "SELECTION_DIGEST_INVALID")
    try:
        driver, abi, khz = _engine_fields(data, "SELECTION_FIELDS_INVALID")
    except EngineNotReady as exc:
        raise EngineNotReady("SELECTION_" + exc.code) from None
    verify_installed(root, openocd_sha256=data["openocd_sha256"],
                     admission_sha256=data["admission_sha256"], require_root=require_root)
    return EngineSelection(root, data["openocd_sha256"], data["admission_sha256"], driver,
                           abi, khz, hashlib.sha256(raw).hexdigest())


# --- install ------------------------------------------------------------------------

def _verify_sidecar(artifact: Path, sidecar: Path) -> str:
    try:
        fields = sidecar.read_text(encoding="utf-8").split()
    except OSError:
        raise EngineNotReady("SIDECAR_UNREADABLE") from None
    _need(len(fields) == 2 and fields[1].lstrip("*") == artifact.name, "SIDECAR_NAME_MISMATCH")
    _need(re.fullmatch(r"[0-9a-f]{64}", fields[0].lower()) is not None, "SIDECAR_DIGEST_INVALID")
    digest = _sha256(artifact)
    _need(digest == fields[0].lower(), "ARTIFACT_SHA256_MISMATCH")
    return digest


def _extract(artifact: Path, destination: Path) -> None:
    count = size = 0
    try:
        archive = tarfile.open(artifact, "r:gz")
    except (OSError, tarfile.TarError):
        raise EngineNotReady("ARTIFACT_UNREADABLE") from None
    with archive:
        seen: set[str] = set()
        for member in archive.getmembers():
            name = member.name.rstrip("/")
            pure = PurePosixPath(name)
            _need(bool(name) and not pure.is_absolute() and ".." not in pure.parts
                  and "\\" not in name and pure.as_posix() == name and name not in seen,
                  "ARTIFACT_MEMBER_UNSAFE")
            seen.add(name)
            target = destination / Path(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            _need(member.isfile(), "ARTIFACT_MEMBER_NOT_REGULAR")
            count += 1
            size += member.size
            _need(count <= MAX_MEMBERS and size <= MAX_BYTES, "ARTIFACT_TOO_LARGE")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            _need(source is not None, "ARTIFACT_MEMBER_UNREADABLE")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _elf32_arm(path: Path) -> bool:
    head = path.read_bytes()[:20]
    return (len(head) == 20 and head[:4] == b"\x7fELF" and head[4] == 1 and head[5] == 1
            and int.from_bytes(head[18:20], "little") == 40)


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha256(p)
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def _write_atomic(path: Path, text: str, *, mode: int = 0o644) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def install(artifact: Path, *, sidecar: Path | None = None, base: Path = ENGINE_BASE,
            declared: Mapping[str, Any] | None = None, require_root: bool = True) -> dict[str, Any]:
    """Verify + install (or adopt an identical existing install). ``declared``
    supplies engine fields (driver/ABI/kHz/version) only when the artifact's
    evidence predates them; artifact evidence always wins when present."""
    if require_root:
        _need(os.geteuid() == 0, "ROOT_REQUIRED")
    artifact_sha = _verify_sidecar(artifact, sidecar or Path(str(artifact) + ".sha256"))
    with tempfile.TemporaryDirectory(prefix="plasma-engine-") as tmp:
        x = Path(tmp) / "x"
        x.mkdir()
        _extract(artifact, x)
        binary, admission, scripts = x / "openocd", x / ADMISSION_NAME, x / "tcl"
        _need(binary.is_file() and admission.is_file() and scripts.is_dir(), "ARTIFACT_LAYOUT_INVALID")
        _need(_elf32_arm(binary), "OPENOCD_NOT_ELF32_ARM")
        bin_sha, adm_sha = _sha256(binary), _sha256(admission)
        sums = {}
        for line in (x / "openocd.sha256").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0].lower()
        _need(sums.get("openocd") == bin_sha and sums.get(ADMISSION_NAME) == adm_sha,
              "ARTIFACT_INTERNAL_SHA256_MISMATCH")
        try:
            evidence = json.loads((x / "candidate-evidence.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise EngineNotReady("ARTIFACT_EVIDENCE_UNREADABLE") from None
        _need(isinstance(evidence, dict) and evidence.get("schema") == CANDIDATE_SCHEMA
              and evidence.get("openocd_binary_sha256") == bin_sha
              and evidence.get("site_admission_script_sha256") == adm_sha,
              "ARTIFACT_EVIDENCE_MISMATCH")
        source_sha = evidence.get("openocd_source_sha")
        _need(type(source_sha) is str and re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None,
              "ARTIFACT_SOURCE_SHA_INVALID")
        fields = {k: evidence[k] for k in ("adapter_driver", "driver_abi", "adapter_khz",
                                           "openocd_version") if k in evidence}
        declared_by = "artifact"
        if len(fields) != 4:
            _need(declared is not None, "ARTIFACT_ENGINE_FIELDS_MISSING_DECLARE_THEM")
            fields = {**dict(declared), **fields}
            declared_by = "operator"
        driver, abi, khz = _engine_fields(fields, "ENGINE_FIELDS_INVALID")
        version = fields.get("openocd_version")
        _need(type(version) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None,
              "OPENOCD_VERSION_INVALID")
        runtime_id = f"{version}-{source_sha[:12]}-{driver.replace('_', '-')}-{bin_sha[:12]}-{adm_sha[:12]}"
        _need(RUNTIME_ID.fullmatch(runtime_id) is not None, "RUNTIME_ID_INVALID")
        manifest = {
            "schema": MANIFEST_SCHEMA, "runtime_id": runtime_id, "openocd_version": version,
            "openocd_source_sha": source_sha, "plasma_source_sha": evidence.get("plasma_source_sha"),
            "openocd_sha256": bin_sha, "admission_sha256": adm_sha, "adapter_driver": driver,
            "driver_abi": abi, "adapter_khz": khz, "artifact_sha256": artifact_sha,
            "engine_fields_declared_by": declared_by,
        }
        staged = Path(tmp) / "d"
        (staged / "bin").mkdir(parents=True)
        (staged / "libexec").mkdir()
        (staged / "share" / "openocd").mkdir(parents=True)
        shutil.copyfile(binary, staged / "bin" / "openocd")
        shutil.copyfile(admission, staged / "libexec" / ADMISSION_NAME)
        shutil.copytree(scripts, staged / "share" / "openocd" / "scripts")
        expected = _tree(staged)
        base.mkdir(parents=True, exist_ok=True)
        target = base / runtime_id
        if os.path.lexists(target):
            _need(target.is_dir() and not target.is_symlink(), "INSTALL_TARGET_NOT_DIRECTORY")
            present = {k: v for k, v in _tree(target).items()
                       if k != MANIFEST_NAME and not k.startswith("evidence/")}
            _need(present == expected, "EXISTING_INSTALL_DIFFERS")
            adopted = True
        else:
            for path in staged.rglob("*"):
                path.chmod(0o755 if path.is_dir() or path == staged / "bin" / "openocd" else 0o644)
            staged.chmod(0o755)
            work = base / f".{runtime_id}.tmp-{os.getpid()}"
            shutil.copytree(staged, work)
            os.replace(work, target)
            adopted = False
        manifest_path = target / MANIFEST_NAME
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if manifest_path.exists():
            _need(json.loads(manifest_path.read_text(encoding="utf-8")) == manifest,
                  "EXISTING_MANIFEST_DIFFERS")
        else:
            _write_atomic(manifest_path, text)
    verify_installed(target, openocd_sha256=bin_sha, admission_sha256=adm_sha,
                     require_root=require_root)
    return {"result": "INSTALLED", "runtime_id": runtime_id, "root": str(target),
            "adopted_existing": adopted, **{k: manifest[k] for k in (
                "openocd_sha256", "admission_sha256", "adapter_driver", "driver_abi",
                "adapter_khz", "engine_fields_declared_by")}}


def install_selected_admission(artifact: Path, *, expected_admission_sha256: str,
                               sidecar: Path | None = None,
                               record: Path = ENGINE_SELECTION,
                               base: Path = ENGINE_BASE,
                               require_root: bool = True) -> dict[str, Any]:
    """Side-by-side Admission revision; preserve selected OpenOCD binary and Tcl.

    Verify the incoming CI candidate's Admission source, then clone the exact
    currently selected Engine with only that entry and its manifest changed.
    Never switch selection, restart services or operate hardware here.
    """
    if require_root:
        _need(os.geteuid() == 0, "ROOT_REQUIRED")
    _need(type(expected_admission_sha256) is str and
          re.fullmatch(r"[0-9a-f]{64}", expected_admission_sha256) is not None,
          "EXPECTED_ADMISSION_SHA_INVALID")
    selected = load_engine(record, base=base, require_root=require_root)
    old = selected.openocd_root
    manifest = _manifest(old)
    version, source = manifest.get("openocd_version"), manifest.get("openocd_source_sha")
    _need(type(version) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
          and type(source) is str and re.fullmatch(r"[0-9a-f]{40}", source),
          "SELECTED_ENGINE_PROVENANCE_INVALID")
    _need(manifest.get("openocd_sha256") == selected.openocd_sha256
          and manifest.get("admission_sha256") == selected.admission_sha256,
          "SELECTED_ENGINE_MANIFEST_MISMATCH")
    _need(all(not p.is_symlink() for p in old.rglob("*")),
          "SELECTED_ENGINE_SYMLINK_DENIED")
    original_files = _tree(old)
    archive_sha = _verify_sidecar(
        artifact, sidecar or Path(str(artifact) + ".sha256"))
    with tempfile.TemporaryDirectory(prefix="plasma-admission-") as tmp:
        extracted = Path(tmp) / "artifact"
        extracted.mkdir()
        _extract(artifact, extracted)
        src = extracted / ADMISSION_NAME
        _need(src.is_file() and not src.is_symlink(),
              "ADMISSION_CANDIDATE_MISSING")
        raw = src.read_bytes()
        admission_sha = hashlib.sha256(raw).hexdigest()
        _need(admission_sha == expected_admission_sha256,
              "ADMISSION_CANDIDATE_SHA_MISMATCH")
        _need(admission_sha != selected.admission_sha256, "ADMISSION_UNCHANGED")
        try:
            compile(raw, ADMISSION_NAME, "exec")
            evidence = json.loads(
                (extracted / "candidate-evidence.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, SyntaxError, UnicodeError) as exc:
            raise EngineNotReady("ADMISSION_CANDIDATE_INVALID") from exc
        _need(type(evidence) is dict and
              evidence.get("schema") == CANDIDATE_SCHEMA and
              evidence.get("site_admission_script_sha256") == admission_sha and
              evidence.get("openocd_source_sha") == source and
              type(evidence.get("plasma_source_sha")) is str and
              re.fullmatch(r"[0-9a-f]{40}", evidence["plasma_source_sha"]),
              "ADMISSION_CANDIDATE_PROVENANCE_MISMATCH")
        _need(b"DEVMEM_INDEPENDENT_IMAGES" not in raw,
              "ADMISSION_REMOVED_API_REFERENCE")
        new_id = (f"{version}-{source[:12]}-"
                  f"{selected.adapter_driver.replace('_', '-')}-"
                  f"{selected.openocd_sha256[:12]}-{admission_sha[:12]}")
        _need(RUNTIME_ID.fullmatch(new_id) is not None, "RUNTIME_ID_INVALID")
        target = base / new_id
        _need(not os.path.lexists(target), "ADMISSION_INSTALL_ALREADY_EXISTS")
        stage = base / f".{new_id}.tmp-{os.getpid()}"
        _need(not os.path.lexists(stage), "ADMISSION_INSTALL_STAGE_COLLISION")
        try:
            shutil.copytree(old, stage, symlinks=True)
            entry = stage / "libexec" / ADMISSION_NAME
            entry.write_bytes(raw)
            entry.chmod(0o644)
            new_manifest = dict(manifest)
            new_manifest.update({
                "runtime_id": new_id, "admission_sha256": admission_sha,
                "admission_source_sha": evidence["plasma_source_sha"],
                "admission_source_artifact_sha256": archive_sha,
                "source_engine_runtime_id": old.name,
                "source_engine_manifest_sha256":
                    hashlib.sha256((old / MANIFEST_NAME).read_bytes()).hexdigest(),
            })
            (stage / MANIFEST_NAME).write_text(
                json.dumps(new_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
            changed = {k for k in original_files.keys() | _tree(stage).keys()
                       if original_files.get(k) != _tree(stage).get(k)}
            _need(changed == {f"libexec/{ADMISSION_NAME}", MANIFEST_NAME},
                  "ADMISSION_ONLY_FILE_DELTA_INVALID")
            _need(_sha256(stage / "bin/openocd") == selected.openocd_sha256,
                  "OPENOCD_BINARY_CHANGED")
            os.replace(stage, target)
            verify_installed(target, openocd_sha256=selected.openocd_sha256,
                             admission_sha256=admission_sha, require_root=require_root)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {
        "result": "ADMISSION_INSTALLED_NOT_SELECTED", "runtime_id": new_id,
        "previous_runtime_id": old.name,
        "openocd_sha256": selected.openocd_sha256,
        "previous_admission_sha256": selected.admission_sha256,
        "admission_sha256": admission_sha,
        "selection_changed": False, "service_restarted": False,
        "fpga_reloaded": False, "flash": "NOT_RUN",
    }


# --- select / list ---------------------------------------------------------------------

def _manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EngineNotReady("ENGINE_NOT_INSTALLED_BY_TOOL") from None
    except (OSError, ValueError):
        raise EngineNotReady("ENGINE_MANIFEST_UNREADABLE") from None
    _need(isinstance(data, dict) and data.get("schema") == MANIFEST_SCHEMA
          and data.get("runtime_id") == root.name, "ENGINE_MANIFEST_INVALID")
    return data


def selection_record(root: Path, manifest: Mapping[str, Any],
                     adapter_khz: int | None = None) -> dict[str, Any]:
    """``adapter_khz``: the Runtime's chosen SWCLK (default: the engine's
    driver default from its manifest)."""
    return {"schema": ENGINE_SCHEMA, "openocd_root": str(root),
            "openocd_sha256": manifest["openocd_sha256"],
            "admission_sha256": manifest["admission_sha256"],
            "adapter_driver": manifest["adapter_driver"], "driver_abi": manifest["driver_abi"],
            "adapter_khz": manifest["adapter_khz"] if adapter_khz is None else adapter_khz}


def select(runtime_id: str, *, record: Path = ENGINE_SELECTION, base: Path = ENGINE_BASE,
           restart: bool = False, require_root: bool = True, adapter_khz: int | None = None,
           hold_gate: Callable[[], Any] | None = None,
           run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict[str, Any]:
    if require_root:
        _need(os.geteuid() == 0, "ROOT_REQUIRED")
    _need(RUNTIME_ID.fullmatch(runtime_id) is not None, "RUNTIME_ID_INVALID")
    root = base / runtime_id
    _need(root.is_dir() and not root.is_symlink(), "ENGINE_NOT_INSTALLED")
    manifest = _manifest(root)
    _engine_fields(manifest, "ENGINE_MANIFEST_INVALID")
    verify_installed(root, openocd_sha256=str(manifest.get("openocd_sha256")),
                     admission_sha256=str(manifest.get("admission_sha256")),
                     require_root=require_root)
    if adapter_khz is not None:
        _need(type(adapter_khz) is int and 0 < adapter_khz <= 100_000, "ADAPTER_KHZ_INVALID")
    new = selection_record(root, manifest, adapter_khz)
    previous = None
    if record.exists():
        with contextlib.suppress(OSError, ValueError, AttributeError):
            previous = json.loads(record.read_text(encoding="utf-8")).get("openocd_root")

    def apply() -> None:
        record.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(record, json.dumps(new, indent=2, sort_keys=True) + "\n")
        load_engine(record, base=base, require_root=require_root)  # the Worker's own check
        if restart:
            r = run(["systemctl", "restart", WORKER_UNIT], capture_output=True, text=True,
                    timeout=120)
            _need(r.returncode == 0, "WORKER_RESTART_FAILED")

    if restart:
        gate = hold_gate or _runtime_gate
        with gate():  # no Runtime Job may run while the Worker restarts
            apply()
    else:
        apply()
    return {"result": "SELECTED", "runtime_id": runtime_id, "previous_root": previous,
            "record": str(record), "worker_restarted": restart, **new}


def _runtime_gate():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ppu_asset_set import held_runtime_asset_lease  # noqa: PLC0415
    return held_runtime_asset_lease()


def list_engines(*, record: Path = ENGINE_SELECTION, base: Path = ENGINE_BASE,
                 require_root: bool = True) -> dict[str, Any]:
    selected = None
    try:
        selected = str(load_engine(record, base=base, require_root=require_root).openocd_root)
        state = "READY"
    except EngineNotReady as exc:
        state = "NOT_READY:" + exc.code
    engines = []
    if base.is_dir():
        for root in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
            try:
                manifest = _manifest(root)
                info = {k: manifest.get(k) for k in ("adapter_driver", "driver_abi", "adapter_khz",
                                                    "openocd_sha256")}
            except EngineNotReady as exc:
                info = {"manifest": exc.code}
            engines.append({"runtime_id": root.name, "selected": str(root) == selected, **info})
    return {"selection": state, "selected_root": selected, "engines": engines}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("install")
    p.add_argument("artifact", type=Path)
    p.add_argument("--sidecar", type=Path)
    p.add_argument("--declare-adapter-driver")
    p.add_argument("--declare-driver-abi", type=int)
    p.add_argument("--declare-adapter-khz", type=int)
    p.add_argument("--declare-openocd-version")
    a = sub.add_parser("install-selected-admission")
    a.add_argument("artifact", type=Path)
    a.add_argument("--sidecar", type=Path)
    a.add_argument("--expected-admission-sha256", required=True)
    s = sub.add_parser("select")
    s.add_argument("runtime_id")
    s.add_argument("--restart", action="store_true")
    s.add_argument("--adapter-khz", type=int,
                   help="Runtime SWCLK in kHz (default: the engine's driver default)")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            declared = {k: v for k, v in {
                "adapter_driver": args.declare_adapter_driver,
                "driver_abi": args.declare_driver_abi,
                "adapter_khz": args.declare_adapter_khz,
                "openocd_version": args.declare_openocd_version}.items() if v is not None}
            out = install(args.artifact, sidecar=args.sidecar, declared=declared or None)
        elif args.command == "install-selected-admission":
            out = install_selected_admission(
                args.artifact, expected_admission_sha256=args.expected_admission_sha256,
                sidecar=args.sidecar)
        elif args.command == "select":
            out = select(args.runtime_id, restart=args.restart, adapter_khz=args.adapter_khz)
        else:
            out = list_engines()
    except EngineNotReady as exc:
        print(json.dumps({"result": "REFUSED", "code": exc.code}), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
