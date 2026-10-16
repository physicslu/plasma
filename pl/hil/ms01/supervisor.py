"""Default-dry-run MS01 load/test/restore supervisor. No SSH or implicit deployment.

The parent never opens MMIO. A durable checkpoint precedes each control write.
An explicit recover-only invocation can resume after a supervisor crash; a
possibly stalled AXI bus requires independent external recovery, never retry.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import uuid
from urllib.parse import urlparse
from urllib.request import urlopen

from pl.hil.ms01 import native as n
from pl.hil.swd04.staging import bit_payload

REPO = Path(__file__).resolve().parents[3]
DEVICES = ("40000000.fabric", "43c00000.audio-codec-ctrl")
DRIVER = "uio_pdrv_genirq"
SERVICES = ("jupyter.service", "plasma-bootstrap.service", "plasma-server.service",
            "plasma-web.service", "plasma-runtime-activation.service")
OWNER_LOCK = Path("/run/lock/plasma-mmio.lock")
CONFIG_LOCK = Path("/run/lock/plasma-ms01-supervisor.lock")


class Stop(RuntimeError):
    """No-go or failed operation; never replay data operations."""


class UnsafeStall(Stop):
    """Timeout/signal/surviving child: software cannot establish AXI safety."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise Stop(why)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_files() -> dict[str, str]:
    paths = set()
    for folder in ("pl/hil/ms01", "pl/hil/lt02", "pl/hil/swd04"):
        paths.update((REPO / folder).glob("*.py"))
    paths.update((REPO / "pl/projects").glob("*/artifact.py"))
    paths.update((REPO / "software/python/plasma_interfaces").glob("*.py"))
    return {str(p.relative_to(REPO)): digest(p) for p in sorted(paths)}


def seal_plan(template: dict, output: Path) -> str:
    """Host-only helper after commit: bind runtime revision separately from BIT."""
    require(not subprocess.check_output(
        ["git", "-C", str(REPO), "diff", "HEAD", "--name-only"], text=True).strip(),
        "Commit runtime source before sealing")
    data = {**template, "runtime_source_sha": subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "runtime_files": runtime_files()}
    # Reject untracked Python from the runtime bundle as well.
    for name, sha in data["runtime_files"].items():
        raw = subprocess.check_output(["git", "-C", str(REPO), "show",
                                       data["runtime_source_sha"] + ":" + name])
        require(hashlib.sha256(raw).hexdigest() == sha, "Uncommitted runtime: " + name)
    write_new(output, data)
    return digest(output)


def write_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


@dataclass(frozen=True)
class Plan:
    data: dict
    sha256: str
    artifact: dict

    @classmethod
    def read(cls, path: Path, expected: str) -> Plan:
        require(bool(re.fullmatch(r"[0-9a-f]{64}", expected)), "Pin exact plan SHA256")
        require(digest(path) == expected, "Plan digest mismatch")
        data = json.loads(path.read_text())
        for key in ("fpga_source_sha", "runtime_source_sha"):
            require(bool(re.fullmatch(r"[0-9a-f]{40}", data[key])), "Invalid source SHA")
        require(data["runtime_files"] == runtime_files(), "Runtime source bytes changed")
        for key in ("manifest", "bit", "hwh", "candidate_bin", "recovery_bin", "recovery_hwh"):
            require(Path(data[key]).is_absolute(), "Artifact paths must be absolute")
        artifact = n.verify_artifacts(
            **{k: Path(data[k]) for k in ("manifest", "bit", "hwh", "candidate_bin",
                                        "recovery_bin", "recovery_hwh")},
            expected_manifest_sha256=data["manifest_sha256"],
            expected_candidate_bin_sha256=data["candidate_bin_sha256"])
        require(artifact["source_git_sha"] == data["fpga_source_sha"], "FPGA source mismatch")
        require(data["recovery_bin_sha256"] == n.swd04_contract.RECOVERY_BIN_SHA256
                and data["recovery_hwh_sha256"] == n.swd04_contract.RECOVERY_HWH_SHA256,
                "Unreviewed recovery pair")
        payload = bit_payload(Path(data["bit"]).read_bytes())
        expected_bin = b"".join(payload[i:i + 4][::-1] for i in range(0, len(payload), 4))
        require(Path(data["candidate_bin"]).read_bytes() == expected_bin + bytes.fromhex("00000020"),
                "BIN conversion is not the exact reviewed Zynq payload")
        require(type(data["iterations"]) is int and 1 <= data["iterations"] <= 10000,
                "Invalid iterations")
        require(type(data["trials"]) is int and 1 <= data["trials"] <= 3, "Invalid trials")
        sizes = data["payload_sizes"]
        require(type(sizes) is list and 1 <= len(sizes) <= 3 and all(
            type(v) is int and 1 <= v <= 1048576 for v in sizes), "Invalid payload matrix")
        require(type(data["worker_timeout_s"]) is int and 1 <= data["worker_timeout_s"] <= 7200,
                "Invalid worker budget")
        paths = {"gateway_live": "/api/health/live", "gateway_ready": "/api/health/ready",
                 "bootstrap": "/v1/health", "jupyter_login": "/login", "jupyter_api": "/api"}
        require(set(data["health_urls"]) == set(paths), "Exact health endpoints required")
        for key, url in data["health_urls"].items():
            parsed = urlparse(url)
            require(parsed.scheme == "http" and parsed.path == paths[key]
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                    and parsed.port in (18080, 18081, 9090, 8888), "Invalid health URL")
        return cls(data, expected, artifact)


class Journal:
    """Atomic, fsync'd immutable numbered checkpoints; pending writes are inert."""
    def __init__(self, output: Path, *, create: bool = False, plan: Plan | None = None):
        self.output = output
        if create:
            output.mkdir(mode=0o700, parents=False)
            require(plan is not None, "Plan required")
            write_new(output / "plan.json", plan.data)
        checkpoints = sorted(output.glob("[0-9][0-9][0-9][0-9]-state.json"))
        self.sequence = len(checkpoints)
        for index, checkpoint in enumerate(checkpoints, 1):
            require(checkpoint.name == f"{index:04d}-state.json", "Journal checkpoint gap")
            require(json.loads(checkpoint.read_text())["sequence"] == index, "Journal sequence mismatch")
        self.state = json.loads(checkpoints[-1].read_text()) if checkpoints else {}

    def save(self, phase: str, **updates) -> None:
        self.sequence += 1
        self.state = {**self.state, **updates, "phase": phase, "sequence": self.sequence}
        pending = self.output / f".pending-{self.sequence:04d}-{uuid.uuid4().hex}"
        write_new(pending, self.state)
        final = self.output / f"{self.sequence:04d}-state.json"
        require(not final.exists(), "Never overwrite a journal checkpoint")
        os.rename(pending, final)
        fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Controller:
    """State machine; adapter injection is for offline fault tests only."""
    def __init__(self, adapter, journal: Journal, plan: Plan):
        self.a, self.j, self.plan = adapter, journal, plan

    def run(self) -> dict:
        try:
            self.a.claim_mmio()
            original = self.a.snapshot()
            self.j.save("PREFLIGHT", original=original, image_touched=False,
                        original_restored=False, release_intents=[], data_test="NOT_RUN",
                        fpga_source_sha=self.plan.data["fpga_source_sha"],
                        runtime_source_sha=self.plan.data["runtime_source_sha"],
                        plan_sha256=self.plan.sha256)
            bindings = original["bindings"]
            self.a.quiescent(frozenset(k for k, v in bindings.items() if v))
            for device, driver in bindings.items():
                if driver is None:
                    continue
                self.j.save("UNBIND_INTENT", release_intents=[*self.j.state["release_intents"], device])
                self.a.unbind(device, driver)
            self.a.quiescent(frozenset())
            self.j.save("LOAD_INTENT", image_touched=True)
            self.a.candidate()
            self.a.receipt()
            self.j.save("CANDIDATE_LOADED")
            self.a.release_mmio()
            self.j.save("WORKER_INTENT")
            self.a.worker()
            self.j.save("TEST_DONE", data_test="PASS")
        except UnsafeStall as exc:
            self.j.save("EXTERNAL_RECOVERY_REQUIRED", error=str(exc), recovery="NOT_RUN",
                        result="FAIL", axi_safety="UNKNOWN")
            return self.j.state
        except Exception as exc:
            self.j.save("FAILED", error=str(exc), result="FAIL")
        return self.recover()

    def recover(self) -> dict:
        require(self.j.state.get("phase") != "EXTERNAL_RECOVERY_REQUIRED",
                "AXI safety unknown: no automatic reload; independent external recovery required")
        if "original" not in self.j.state:
            self.j.save("NO_GO", result="FAIL", recovery="NOT_RUN")
            return self.j.state
        original = self.j.state["original"]
        if not self.j.state.get("image_touched") and not self.j.state.get("release_intents"):
            self.j.save("NO_GO", result="FAIL", recovery="NOT_NEEDED")
            return self.j.state
        try:
            self.a.claim_mmio()  # A competing owner blocks restoration, never bypass it.
            self.a.child_dead(self.j.state.get("active_child"))
            self.a.child_terminal(self.j.state)
            self.a.quiescent(frozenset(k for k, v in original["bindings"].items() if v))
            if self.j.state.get("image_touched") and not self.j.state.get("original_restored"):
                self.a.quiescent(frozenset())
                self.j.save("RESTORE_INTENT")
                self.a.restore()
                self.j.save("ORIGINAL_LOADED", original_restored=True)
            errors = []
            for device, driver in original["bindings"].items():
                self.j.save("REBIND_INTENT", rebind_device=device)
                try:
                    self.a.bind(device, driver)
                except Exception as exc:
                    errors.append(f"{device}: {exc}")
            verification = self.a.verify(original)  # Independent fresh observation, not load rc.
            require(not errors and bool(verification) and all(verification.values()),
                    "Recovery verification/rebind failed: " + repr((errors, verification)))
            self.j.save("RECOVERY_VERIFIED", recovery="PASS", verification=verification,
                        result="PASS" if self.j.state.get("data_test") == "PASS"
                        and not self.j.state.get("error") else "FAIL")
        except UnsafeStall as exc:
            self.j.save("EXTERNAL_RECOVERY_REQUIRED", error=str(exc), recovery="FAIL",
                        result="FAIL", axi_safety="UNKNOWN")
        except Exception as exc:
            self.j.save("RECOVERY_FAILED", recovery="FAIL", recovery_error=str(exc), result="FAIL")
        return self.j.state


def protected(path: Path) -> None:
    s = path.lstat()
    require(s.st_uid == 0 and not s.st_mode & 0o022 and not path.is_symlink(),
            "Root-protected path required: " + str(path))


def lock_file(path: Path) -> int:
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and not s.st_mode & 0o077 and s.st_nlink == 1, "Unsafe lock inode")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


class LinuxAdapter:
    """Explicit live-only local Z2 adapter. No parent MMIO, SSH, or service writes."""
    def __init__(self, plan: Plan, journal: Journal):
        self.p, self.j = plan, journal
        self.config_fd: int | None = None
        self.mmio_fd: int | None = None
        self.platform_root = Path("/sys/bus/platform")
        self.firmware = "plasma-ms01-" + hashlib.sha256(str(journal.output).encode()).hexdigest()[:16] + ".bin"

    def __enter__(self):
        require(os.geteuid() == 0, "Authorized target root required")
        n.check_runtime()  # Rejects SWPC even with live flags; no sudo or runtime substitution.
        protected(self.j.output)
        for key in ("candidate_bin", "recovery_bin", "recovery_hwh", "bit", "hwh", "manifest"):
            path = Path(self.p.data[key])
            protected(path)
            protected(path.parent)
        self.runtime_intact()
        self.config_fd = lock_file(CONFIG_LOCK)
        return self

    def __exit__(self, *_):
        self.release_mmio()
        if self.config_fd is not None:
            # Never LOCK_UN: a surviving child inherits this same open description.
            os.close(self.config_fd)
            self.config_fd = None

    def claim_mmio(self):
        if self.mmio_fd is None:
            self.mmio_fd = lock_file(OWNER_LOCK)

    def release_mmio(self):
        if self.mmio_fd is not None:
            os.close(self.mmio_fd)
            self.mmio_fd = None

    @staticmethod
    def _cmd(args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=10).stdout

    def runtime_intact(self):
        require(runtime_files() == self.p.data["runtime_files"], "Runtime changed after plan verification")
        for name in self.p.data["runtime_files"]:
            path = REPO / name
            protected(path)
            protected(path.parent)

    def same_boot(self):
        original = self.j.state.get("original")
        if original:
            require(Path("/proc/sys/kernel/random/boot_id").read_text().strip()
                    == original["boot_id"], "Boot changed: journal cannot authorize new hardware writes")

    def _driver(self, device):
        require(device in DEVICES, "Unreviewed platform device")
        link = self.platform_root / "devices" / device / "driver"
        if not link.exists() and not link.is_symlink():
            return None
        require(link.resolve(strict=True) == self.platform_root / "drivers" / DRIVER,
                "Unexpected original driver")
        return DRIVER

    def snapshot(self):
        manager = Path("/sys/class/fpga_manager/fpga0")
        kernel = self._cmd(["dmesg", "--color=never"])
        clock = Path("/sys/kernel/debug/clk/clk_summary").read_text()
        rows = [line.split() for line in clock.splitlines() if line.split() and line.split()[0] == "fclk0"]
        require(len(rows) == 1 and int(rows[0][4]) == 100000000 and int(rows[0][2]) > 0,
                "Enabled 100 MHz FCLK0 required")
        services = self._cmd(["systemctl", "show", *SERVICES, "-p", "Id", "-p", "MainPID",
                              "-p", "ActiveState", "-p", "SubState"])
        require(services.count("ActiveState=active") == len(SERVICES), "Original services not active")
        local = json.loads(self._cmd(["ip", "-j", "address", "show"]))
        ips = {a["local"] for nic in local for a in nic.get("addr_info", [])}
        http = {}
        for name, url in self.p.data["health_urls"].items():
            require(urlparse(url).hostname in ips, "Health URL must address this target")
            with urlopen(url, timeout=5) as response:
                response.read(65536)
                http[name] = response.status
        require(all(v == 200 for v in http.values()), "Original HTTP health not ready")
        uio = []
        for u in Path("/sys/class/uio").glob("uio*"):
            uio.append(((u / "name").read_text().strip(),
                        (u / "device/driver").resolve().name if (u / "device/driver").exists() else None,
                        sorted((int((m / "addr").read_text(), 0), int((m / "size").read_text(), 0))
                               for m in (u / "maps").glob("map*"))))
        metadata = {str(p): digest(p) for p in Path("/home/xilinx/pynq/pl_server").iterdir()
                    if p.name == "_current_metadata.pkl" or p.name.startswith("global_pl_state_") and p.suffix == ".json"}
        require(bool(metadata), "Original metadata missing")
        protected(Path("/lib/firmware/base.bin"))
        protected(Path("/home/xilinx/pynq/overlays/base/base.hwh"))
        require(digest(Path("/lib/firmware/base.bin")) == self.p.data["recovery_bin_sha256"]
                and digest(Path("/home/xilinx/pynq/overlays/base/base.hwh")) == self.p.data["recovery_hwh_sha256"],
                "Installed original recovery files changed")
        return {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "manager": (manager / "state").read_text().strip(),
                "flags": (manager / "flags").read_text().strip(),
                "last_load": n.last_load(kernel), "kernel": kernel.splitlines(),
                "clock": rows[0], "services": services, "http": http,
                "uio": sorted(uio), "metadata": metadata,
                "bindings": {device: self._driver(device) for device in DEVICES}}

    def quiescent(self, allowed):
        self.same_boot()
        require(allowed <= set(DEVICES), "Only reviewed original drivers may be admitted")
        n.check_ownership(full_reconfiguration=True, allowed_kernel_devices=allowed)
        if "original" not in self.j.state or not self.j.state.get("image_touched"):
            manager = Path("/sys/class/fpga_manager/fpga0")
            require((manager / "state").read_text().strip() == "operating"
                    and (manager / "flags").read_text().strip() == "0", "Manager not ready")
            require("writing base.bin " in n.last_load(self._cmd(["dmesg", "--color=never"])),
                    "Unknown original image: cannot establish restoration identity")

    def unbind(self, device, driver):
        self.same_boot()
        require(driver == DRIVER and self._driver(device) == driver, "Binding changed before unbind")
        (self.platform_root / "drivers" / driver / "unbind").write_text(device)
        require(self._driver(device) is None, "Unbind not observed")

    def bind(self, device, driver):
        self.same_boot()
        current = self._driver(device)
        if current == driver:
            return
        require(current is None and driver == DRIVER, "Unexpected binding; do not mutate it")
        (self.platform_root / "drivers" / driver / "bind").write_text(device)
        require(self._driver(device) == driver, "Rebind not observed")

    @staticmethod
    def child_dead(child):
        if child is None:
            return
        path = Path(f"/proc/{child['pid']}/stat")
        try:
            text = path.read_text()
        except FileNotFoundError:
            return
        start = text[text.rfind(")") + 2:].split()[19]
        require(start != child["start_ticks"], "Admitted child remains alive: do not reload")

    def child_terminal(self, state):
        name = state.get("child_terminal")
        if name is None:
            return
        path = self.j.output / name
        if not path.is_file():
            raise UnsafeStall("No durable child completion; AXI/controller state unknown")
        info = json.loads(path.read_text())
        require(info["stage"] == state["child_stage"], "Child completion stage mismatch")
        self.child_dead(info)

    def _child(self, label, code, budget):
        require(self.config_fd is not None, "Configuration exclusion required")
        terminal = f"child-{self.j.sequence:04d}-{label}-terminal.json"
        self.j.save("CHILD_INTENT", child_terminal=terminal, child_stage=label, active_child=None)
        terminal_path = self.j.output / terminal
        wrapper = (f"CODE={code!r}\nSTAGE={label!r}\nTERMINAL={str(terminal_path)!r}\n"
                   + """import os, sys, json, traceback
from pathlib import Path
rc = 0
try:
    exec(CODE)
except SystemExit as exc:
    rc = exc.code if isinstance(exc.code, int) else 1
except BaseException:
    traceback.print_exc()
    rc = 1
text = Path('/proc/self/stat').read_text()
info = {'stage': STAGE, 'pid': os.getpid(),
        'start_ticks': text[text.rfind(')') + 2:].split()[19], 'returncode': rc}
path = Path(TERMINAL)
with path.open('x') as handle:
    json.dump(info, handle); handle.flush(); os.fsync(handle.fileno())
fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
os.fsync(fd); os.close(fd)
sys.exit(rc)
""")
        with (self.j.output / f"{label}-{self.j.sequence}.stdout").open("x") as out, \
                (self.j.output / f"{label}-{self.j.sequence}.stderr").open("x") as err:
            # Loader children also retain the global MMIO gate if the parent dies.
            inherited = (self.config_fd,) + ((self.mmio_fd,) if self.mmio_fd is not None else ())
            child = subprocess.Popen([sys.executable, "-I", "-B", "-c", wrapper], stdout=out,
                                     stderr=err, pass_fds=inherited)
            try:
                text = Path(f"/proc/{child.pid}/stat").read_text()
                ticks = text[text.rfind(")") + 2:].split()[19]
            except FileNotFoundError:
                ticks = "already-exited"
            self.j.save("CHILD_RUNNING", active_child={"pid": child.pid, "start_ticks": ticks})
            try:
                rc = child.wait(timeout=budget)
            except (subprocess.TimeoutExpired, Stop) as exc:
                child.kill()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                raise UnsafeStall(f"{label} interrupted/timed out; no automatic reload") from exc
            if rc < 0:
                raise UnsafeStall(f"{label} exited by signal {rc}; no AXI recovery guarantee")
            self.child_terminal(self.j.state)
            require(rc == 0, f"{label} failed rc={rc}")
            self.j.save("CHILD_EXITED", active_child=None)

    def _program(self, name):
        self.same_boot()
        before = n.last_load(self._cmd(["dmesg", "--color=never"]))
        require(self.mmio_fd is not None, "Global MMIO lock required during reconfiguration")
        self._child("fpga-manager", "from pathlib import Path; "
                    + f"Path('/sys/class/fpga_manager/fpga0/firmware').write_text({name!r})", 120)
        manager = Path("/sys/class/fpga_manager/fpga0")
        require((manager / "state").read_text().strip() == "operating", "FPGA not operating")
        after = n.last_load(self._cmd(["dmesg", "--color=never"]))
        require(after != before and f"writing {name} " in after,
                "FPGA Manager load not observed")
        require(Path("/proc/sys/kernel/random/boot_id").read_text().strip()
                == self.j.state["original"]["boot_id"], "Boot changed during operation")

    def candidate(self):
        self.runtime_intact()
        require(digest(Path(self.p.data["candidate_bin"])) == self.p.data["candidate_bin_sha256"],
                "Candidate changed after preflight")
        firmware = Path("/lib/firmware") / self.firmware
        protected(firmware.parent)
        with firmware.open("xb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(Path(self.p.data["candidate_bin"]).read_bytes())
            f.flush(); os.fsync(f.fileno())
        require(digest(firmware) == self.p.data["candidate_bin_sha256"], "Staging hash mismatch")
        self._program(self.firmware)

    def receipt(self):
        n.record_load_receipt(self.j.output / "loaded.json", Path("/lib/firmware") / self.firmware,
                              self.p.artifact)

    def worker(self):
        self.runtime_intact()
        require(self.mmio_fd is None, "Worker must acquire production global MMIO lock itself")
        args = []
        for key in ("manifest", "bit", "hwh", "recovery_bin", "recovery_hwh"):
            args += ["--" + key.replace("_", "-"), self.p.data[key]]
        args += ["--candidate-bin", str(Path("/lib/firmware") / self.firmware),
                 "--receipt", str(self.j.output / "loaded.json"),
                 "--output", str(self.j.output / "mmio-results"),
                 "--expected-manifest-sha256", self.p.data["manifest_sha256"],
                 "--expected-candidate-bin-sha256", self.p.data["candidate_bin_sha256"],
                 "--iterations", str(self.p.data["iterations"]), "--trials", str(self.p.data["trials"]),
                 "--payload-sizes", *map(str, self.p.data["payload_sizes"]),
                 "--execute-live", "--ack-unrecoverable-axi-stall-risk"]
        code = (f"import sys; sys.path[:0]={[str(REPO), str(REPO / 'software/python')]!r}; "
                "from pl.hil.ms01 import native; " + f"sys.exit(native.main({args!r}))")
        self._child("mmio-worker", code, self.p.data["worker_timeout_s"])
        result = json.loads((self.j.output / "mmio-results/result.json").read_text())
        require(result["result"] == "PASS" and result["source_git_sha"] == self.p.data["fpga_source_sha"],
                "No actual matching data PASS")

    def restore(self):
        require(digest(Path(self.p.data["recovery_bin"])) == self.p.data["recovery_bin_sha256"]
                and digest(Path("/lib/firmware/base.bin")) == self.p.data["recovery_bin_sha256"],
                "Recovery bytes changed")
        self._program("base.bin")

    def verify(self, original):
        after = self.snapshot()
        write_new(self.j.output / f"recovery-observation-{self.j.sequence}.json", after)
        old, new = original["kernel"], after["kernel"]
        overlap = next((i for i in range(min(len(old), len(new)), 0, -1) if old[-i:] == new[:i]), 0)
        added = new[overlap:]
        allowed = (f"fpga_manager fpga0: writing {self.firmware} to ",
                   "fpga_manager fpga0: writing base.bin to ")
        # JSON checkpoints round-trip tuples to lists; compare canonical JSON.
        same = lambda key: json.dumps(after[key], sort_keys=True) == json.dumps(original[key], sort_keys=True)
        return {"manager_operating": after["manager"] == "operating",
                "flags": after["flags"] == original["flags"] == "0",
                "original_image": "writing base.bin " in after["last_load"],
                "same_boot": same("boot_id"), "clock": same("clock"), "UIO": same("uio"),
                "bindings": same("bindings"), "metadata": same("metadata"),
                "services": same("services"), "HTTP": same("http"),
                "kernel": bool(overlap) and all(any(v in line for v in allowed) for line in added)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--expected-plan-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--execute-live", action="store_true")
    p.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    p.add_argument("--recover-only", action="store_true")
    args = p.parse_args(argv)
    try:
        require(not args.ack_unrecoverable_axi_stall_risk or args.execute_live,
                "Risk flag alone does not authorize execution")
        plan = Plan.read(args.plan, args.expected_plan_sha256)
        if not args.execute_live:
            print(json.dumps({"mode": "DRY_RUN", "hardware": "NOT_RUN",
                              "fpga_source_sha": plan.data["fpga_source_sha"],
                              "runtime_source_sha": plan.data["runtime_source_sha"],
                              "recover_only": args.recover_only,
                              "admission": "Requires fresh live ownership/recovery preflight"}))
            return 0
        require(args.ack_unrecoverable_axi_stall_risk, "Explicit AXI risk flag required")
        require(os.geteuid() == 0, "Authorized root required")
        n.check_runtime()  # Before creating journal or control locks.
        if args.recover_only:
            protected(args.output)
            journal = Journal(args.output)
            require(journal.state.get("plan_sha256") == plan.sha256, "Recovery plan mismatch")
            require(json.loads((args.output / "plan.json").read_text()) == plan.data, "Saved plan changed")
        else:
            journal = Journal(args.output, create=True, plan=plan)
        with LinuxAdapter(plan, journal) as adapter:
            controller = Controller(adapter, journal, plan)
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: (_ for _ in ()).throw(Stop("Supervisor interrupted")))
            result = controller.recover() if args.recover_only else controller.run()
        print(json.dumps(result, indent=2))
        return 0 if result.get("result") == "PASS" else 2
    except (OSError, ValueError, TypeError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
        print("MS01_SUPERVISOR_NO_GO: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
