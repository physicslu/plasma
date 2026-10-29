"""One-command, version-pinned SWPC/Z2 engineering-module deployment.

Separate from the product ``plasmactl`` lifecycle. Deploying only installs
reviewed Python integration code: it never executes OpenOCD, FPGA or DUT jobs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
TARGET_HELPER = REPO / "scripts/ppu_deploy_target.py"
ENGINE = REPO / "scripts/plasma_wordport_program.py"
LOCAL_ROOT = Path.home() / ".local/share/plasma/engineering"
Z2_FILES = (
    "scripts/plasma_wordport_program.py",
    "scripts/bluepill-wordport-session.py",
    "software/python/plasma_interfaces/native_bluepill_word_port.py",
    "software/python/plasma_interfaces/wordport_stage_monitor.py",
    "software/python/plasma_interfaces/bluepill_remote_bitbang.py",
)
SWPC_FILES = ("scripts/plasma_wordport_program.py", "scripts/plasma_ab_burn_in.py")
MODULES = ("wordport", "openocd-integration", "abtest")
HEX40 = re.compile(r"[a-f0-9]{40}\Z")


class DeploymentError(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".ppu-deploy-", delete=False) as file:
        temporary = Path(file.name)
        file.write(text)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def committed_main() -> str:
    def git(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=10, check=True)
        return done.stdout.strip()
    if git("branch", "--show-current") != "main" or git("status", "--porcelain"):
        raise DeploymentError("DEPLOY_REQUIRES_CLEAN_COMMITTED_MAIN")
    head = git("rev-parse", "HEAD")
    if head != git("rev-parse", "origin/main"):
        raise DeploymentError("MAIN_AND_ORIGIN_MAIN_DIFFER")
    remote = git("ls-remote", "origin", "refs/heads/main").split()
    if len(remote) != 2 or remote[0] != head or remote[1] != "refs/heads/main":
        raise DeploymentError("REMOTE_MAIN_HAS_CHANGED_OR_CANNOT_BE_CONFIRMED")
    return head


def build_bundle(module: str, commit: str) -> tuple[dict, bytes, dict[str, bytes]]:
    if module not in MODULES or not HEX40.fullmatch(commit):
        raise DeploymentError("INVALID_MODULE_OR_COMMIT")
    remote = {relative: (REPO / relative).read_bytes() for relative in Z2_FILES}
    local_names = SWPC_FILES if module == "abtest" else SWPC_FILES[:1]
    local = {relative: (REPO / relative).read_bytes() for relative in local_names}
    manifest = {"schema": "plasma.ppu.deploy.v1", "module": module,
                "source_commit": commit,
                "z2_files": {key: sha(value) for key, value in remote.items()},
                "swpc_files": {key: sha(value) for key, value in local.items()},
                "target_helper_sha256": sha(TARGET_HELPER.read_bytes())}
    manifest["bundle_sha256"] = sha(json.dumps(manifest, sort_keys=True).encode())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for relative, data in remote.items():
            archive.writestr(relative, data)
    return manifest, buffer.getvalue(), local


def unified_api_plan(module: str, commit: str, archive: bytes) -> dict:
    """Host-only cross-entry plan: the Bootstrap endpoint is the only target.

    Engineering module installs are still NOT_QUALIFIED there. Existing
    SSH deployments are preserved during migration, not counted as migrated.
    """
    spec = importlib.util.spec_from_file_location(
        "ppu_unified_deployment", REPO / "scripts/ppu_unified_deployment.py"
    )
    if spec is None or spec.loader is None:
        raise DeploymentError("UNIFIED_DEPLOYMENT_CONTRACT_MISSING")
    unified = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = unified
    spec.loader.exec_module(unified)
    intent = unified.plan_unified_deployment(
        unified.DeploymentKind.ENGINEERING_MODULE,
        source_commit=commit,
        artifact_sha256=sha(archive),
        module=module,
    )
    return intent.to_descriptor()


class Deployer:
    def __init__(self, local_root: Path = LOCAL_ROOT):
        self.root = local_root

    def _remote(self, action: str, payload: bytes = b"") -> dict:
        spec = importlib.util.spec_from_file_location("ppu_deploy_transport", ENGINE)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        try:
            credentials, hosts = engine.z2_login_credentials(Path.home())
        except engine.NotRun as error:
            raise DeploymentError("Z2_CREDENTIAL_ADMISSION_FAILED:" + str(error)) from error
        encoded = base64.b64encode(payload).decode("ascii")
        if len(encoded) > 90_000:
            raise DeploymentError("DEPLOYMENT_PACKAGE_EXCEEDS_BOUNDED_SSH_COMMAND")
        command = [engine.PYTHON, "-I", "-c", TARGET_HELPER.read_text(),
                   action, "--payload", encoded]
        try:
            status, output = engine.password_ssh_z2(command, credentials, hosts, timeout=180)
        except engine.NotRun as error:
            raise DeploymentError("Z2_TRANSPORT_ADMISSION_FAILED:" + str(error)) from error
        result = None
        for line in reversed(output.splitlines()):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and "result" in obj:
                result = obj
                break
        if status != 0 or result is None or result.get("result") != "PASS":
            raise DeploymentError("Z2_" + (result.get("reason", "DEPLOYMENT_FAILED") if result else "NO_VALID_RECEIPT"))
        return result

    def state(self) -> dict:
        path = self.root / "state.json"
        if self.root.is_symlink() or path.is_symlink():
            raise DeploymentError("SWPC_DEPLOYMENT_STATE_SYMLINK_DENIED")
        if not path.exists():
            return {"current": None, "previous": None}
        record = json.loads(path.read_text())
        if (not isinstance(record, dict) or set(record) != {"current", "previous"} or
                any(value is not None and
                    (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value))
                    for value in record.values())):
            raise DeploymentError("SWPC_STATE_INVALID")
        return record

    def _release(self, version: str) -> Path:
        if not isinstance(version, str) or len(version) != 64 or any(c not in "0123456789abcdef" for c in version):
            raise DeploymentError("INVALID_RELEASE_ID")
        return self.root / "releases" / version

    def _verify_local(self, version: str) -> dict:
        release = self._release(version)
        if release.is_symlink() or (self.root / "releases").is_symlink():
            raise DeploymentError("SWPC_RELEASE_SYMLINK_DENIED")
        manifest = json.loads((release / "manifest.json").read_text())
        if manifest.get("bundle_sha256") != version:
            raise DeploymentError("SWPC_RELEASE_ID_MISMATCH")
        allowed = set(SWPC_FILES)
        if (not isinstance(manifest.get("swpc_files"), dict) or
                not manifest["swpc_files"] or
                set(manifest["swpc_files"]) - allowed):
            raise DeploymentError("SWPC_RELEASE_MANIFEST_INVALID")
        for relative, expected in manifest["swpc_files"].items():
            file = release / relative
            if not file.is_file() or file.is_symlink() or sha(file.read_bytes()) != expected:
                raise DeploymentError("SWPC_FILE_SHA_MISMATCH:" + relative)
        return manifest

    def _stage_local(self, manifest: dict, files: dict[str, bytes]) -> Path:
        release = self._release(manifest["bundle_sha256"])
        if self.root.is_symlink() or (self.root / "releases").is_symlink() or release.is_symlink():
            raise DeploymentError("SWPC_RELEASE_SYMLINK_DENIED")
        if release.exists():
            self._verify_local(manifest["bundle_sha256"])
            return release
        releases = release.parent
        releases.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ppu-release-", dir=releases) as temporary:
            staged = Path(temporary)
            for relative, data in files.items():
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o644)
            atomic_text(staged / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
            staged.rename(release)
        self._verify_local(manifest["bundle_sha256"])
        return release

    def _activate_local(self, current: str | None, previous: str | None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        link = self.root / "current"
        if link.exists() and not link.is_symlink():
            raise DeploymentError("SWPC_CURRENT_NOT_SYMLINK")
        if current is not None:
            self._verify_local(current)
            target = self._release(current)
            temporary = self.root / ".current-next"
            if temporary.exists() or temporary.is_symlink():
                raise DeploymentError("SWPC_PENDING_ACTIVATION_EXISTS")
            temporary.symlink_to(target, target_is_directory=True)
            os.replace(temporary, link)
        elif link.is_symlink():
            link.unlink()
        atomic_text(self.root / "state.json", json.dumps({"current": current, "previous": previous},
                                                         sort_keys=True, indent=2))

    def deploy(self, module: str) -> dict:
        commit = committed_main()
        manifest, archive, local = build_bundle(module, commit)
        before = self.state()
        version = manifest["bundle_sha256"]
        remote_before = self._remote("status").get("current")
        remote_version = remote_before.get("bundle_sha256") if remote_before else None
        if remote_version != before["current"]:
            raise DeploymentError("SWPC_Z2_PREVIOUS_VERSION_MISMATCH")
        if before["current"] == version:
            self._verify_local(version)
            self._remote("verify", json.dumps(manifest).encode())
            return {"result": "PASS", "mode": "NO_CHANGE", "source_commit": commit}
        self._stage_local(manifest, local)
        self._remote("deploy", archive)
        try:
            self._activate_local(version, before["current"])
            self.verify()
        except Exception:
            try:
                self._remote("rollback")
                self._activate_local(before["current"], before["previous"])
            except DeploymentError as error:
                raise DeploymentError("SWPC_ACTIVATION_AND_Z2_RECOVERY_FAILED:" + str(error)) from error
            raise
        return {"result": "PASS", "mode": "ACTIVATED", "source_commit": commit,
                "bundle_sha256": version}

    def verify(self) -> dict:
        state = self.state()
        if not state["current"]:
            raise DeploymentError("NO_ACTIVE_SWPC_RELEASE")
        manifest = self._verify_local(state["current"])
        if not (self.root / "current").is_symlink() or (self.root / "current").resolve() != self._release(state["current"]):
            raise DeploymentError("SWPC_ACTIVE_RELEASE_MISMATCH")
        remote = self._remote("status").get("current")
        if remote is None or remote.get("bundle_sha256") != state["current"]:
            raise DeploymentError("SWPC_Z2_ACTIVE_VERSION_MISMATCH")
        self._remote("verify", json.dumps(manifest).encode())
        return {"result": "PASS", "source_commit": manifest["source_commit"],
                "module": manifest["module"], "bundle_sha256": state["current"]}

    def rollback(self) -> dict:
        state = self.state()
        if not state["current"]:
            raise DeploymentError("NO_ACTIVE_SWPC_RELEASE")
        if state["previous"]:
            self._verify_local(state["previous"])
        self.verify()
        self._remote("rollback")
        self._activate_local(state["previous"], None)
        return {"result": "PASS", "mode": "ROLLED_BACK",
                "restored_bundle": state["previous"]}

    def status(self) -> dict:
        local = self.state()
        remote = self._remote("status")
        return {"result": "PASS", "swpc": local, "z2": remote.get("current")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "deploy", "verify", "rollback", "status"))
    parser.add_argument("module", nargs="?", choices=MODULES)
    args = parser.parse_args(argv)
    try:
        deployer = Deployer()
        if args.action in ("plan", "deploy") and not args.module:
            parser.error("plan/deploy require an approved module")
        if args.action == "plan":
            # Planning does not contact Z2 or mutate local state.
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                    capture_output=True, text=True, check=True, timeout=10).stdout.strip()
            manifest, archive, _ = build_bundle(args.module, commit)
            result = {"result": "PASS", "mode": "PLAN_ONLY", "manifest": manifest,
                      "package_bytes": len(archive), "no_deployment": True,
                      "unified_deployment": unified_api_plan(args.module, commit, archive)}
        elif args.action == "deploy":
            result = deployer.deploy(args.module)
        elif args.action == "verify":
            result = deployer.verify()
        elif args.action == "rollback":
            result = deployer.rollback()
        else:
            result = deployer.status()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (DeploymentError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"result": "NOT_RUN", "reason": str(exc)[:300]}), file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main())
