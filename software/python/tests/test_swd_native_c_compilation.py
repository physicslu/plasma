"""Compile and execute the actual native C SWD FIFO core, HOST-ONLY.

This invokes a Linux hosted C compiler against injected C fake MMIO, not
SWPC Vivado, OpenOCD binary integration, ARMv7 device memory or DUT.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "software/native/swd"


def test_native_c_core_compiles_cleanly_and_blocks_uncertain_replay(tmp_path):
    cc = shutil.which("cc")
    assert cc, "GitHub-hosted C compiler is a required validation dependency"
    executable = tmp_path / "host-only-swd-fifo"
    source = SRC / "plasma_swd_fifo_core.c"
    test = SRC / "tests/test_plasma_swd_fifo_core.c"
    compile_cmd = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-fno-strict-aliasing", "-I", str(SRC),
        str(source), str(test), "-o", str(executable),
    ]
    built = subprocess.run(compile_cmd, text=True, capture_output=True,
                           timeout=30, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    verified = subprocess.run((str(executable),), text=True,
                              capture_output=True, timeout=10, check=False)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "PLASMA_NATIVE_SWD_C_HOST_ONLY_PASS" in verified.stdout


def test_c_core_is_separate_from_hardware_and_retired_debug_mode():
    c = (SRC / "plasma_swd_fifo_core.c").read_text(encoding="utf-8")
    h = (SRC / "plasma_swd_fifo_core.h").read_text(encoding="utf-8")
    assert "PLASMA_SWD_ABI_V5" in h and "PLASMA_SWD_MAX_QUEUE 256u" in h
    # Outstanding commands never exceed the 16-deep RTL command FIFO.
    assert "PLASMA_SWD_PIPELINE_DEPTH 16u" in h
    for forbidden in (
        "/dev/mem\"", "open(", "mmap(", "ioctl(", "system(",
        "MODE_DEBUG", "remote_bitbang", "socket(", "execve(",
    ):
        assert forbidden not in c, forbidden
    assert "PLASMA_SWD_ACK_WAIT" in c and "PLASMA_SWD_ACK_FAULT" in c
    assert "PLASMA_SWD_UNSUPPORTED" in c and "s->blocked" in c


def test_c_opencd_5088_swd_callback_shapes_with_host_only_shim(tmp_path):
    """Fake header verifies C ABI shapes, NOT genuine OpenOCD source build."""
    cc = shutil.which("cc")
    assert cc, "C compiler required"
    executable = tmp_path / "host-only-openocd-callback"
    cmd = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-I", str(SRC),
        "-I", str(SRC / "tests/openocd_shim"),
        "-DPLASMA_SWD_HOST_TEST=1",
        str(SRC / "plasma_swd_fifo_core.c"),
        str(SRC / "plasma_swd_native_words.c"),
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "plasma_swd_lease_word_port.c"),
        str(SRC / "plasma_swd_openocd5088_callbacks.c"),
        str(SRC / "plasma_swd_openocd5088_driver.c"),
        str(SRC / "tests/test_openocd5088_callbacks.c"),
        "-o", str(executable),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    done = subprocess.run([str(executable)], capture_output=True, text=True,
                          timeout=10, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PLASMA_OPENOCD5088_CALLBACK_SHIM_HOST_ONLY_PASS" in done.stdout


def test_native_callback_is_source_locked_and_no_product_adapter_registered():
    src = (SRC / "plasma_swd_openocd5088_callbacks.c").read_text()
    assert "#include <jtag/swd.h>" in src
    assert "struct swd_driver plasma_swd_openocd5088_ops" in src
    for name in (".init", ".switch_seq", ".read_reg", ".write_reg", ".run"):
        assert name in src
    assert "struct adapter_driver" in (SRC / "plasma_swd_openocd5088_driver.c").read_text()
    assert "remote_bitbang_adapter_driver" not in src
    assert "plasma_swd_openocd5088_bind_guarded" in src
    assert "plasma_swd_native_words_ready" in src
    assert "int plasma_swd_openocd5088_bind(" not in src
    assert "plasma_swd_openocd5088_unbind" in src


def test_native_leased_word_port_host_only_owner_revocation(tmp_path):
    """Real C lease-guarded word-port compilation and synthetic owner tests."""
    cc = shutil.which("cc")
    assert cc, "GitHub-hosted C compiler required"
    executable = tmp_path / "host-only-swd-leased"
    cmd = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-I", str(SRC),
        str(SRC / "plasma_swd_fifo_core.c"),
        "-DPLASMA_SWD_HOST_TEST=1",
        str(SRC / "plasma_swd_lease_word_port.c"),
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "tests/test_plasma_swd_lease_word_port.c"),
        "-o", str(executable),
    ]
    compiled = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=30, check=False)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(executable)], capture_output=True,
                            text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PLASMA_NATIVE_SWD_LEASE_PORT_HOST_ONLY_PASS" in result.stdout


def test_native_lease_boundary_has_no_direct_device_or_bitbang_path():
    source = (SRC / "plasma_swd_lease_word_port.c").read_text()
    header = (SRC / "plasma_swd_lease_word_port.h").read_text()
    assert "invalidate_all" in source and "invalidate_all" in header
    assert "read_owned" in source and "write_owned" in source
    assert "barrier_owned" in source and "generation" in source
    for forbidden in ("open(", "mmap(", "ioctl(", "socket(",
                      "MODE_DEBUG", "remote_bitbang", "system("):
        assert forbidden not in source
    assert "0x3c" not in source and "0x40" not in source


def test_c_owner_flock_excludes_existing_python_linuxmmio(tmp_path):
    """Two separate processes use the exact same advisory lock protocol.

    Tests only a temporary lock and synthetic regular file. No /dev/mem.
    """
    from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture, MMIOError

    cc = shutil.which("cc")
    assert cc, "Host C compiler required"
    binary = tmp_path / "plasma-swd-flock-test"
    compile_args = [
        cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-O2", "-I", str(SRC),
        "-DPLASMA_SWD_HOST_TEST=1",
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "tests/test_plasma_swd_owner_lock_cli.c"),
        "-o", str(binary),
    ]
    result = subprocess.run(compile_args, text=True, capture_output=True,
                            timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr

    lock_file = tmp_path / "plasma-mmio.lock"
    fixture = tmp_path / "fake-mmio"
    with fixture.open("wb") as f:
        f.truncate(8192)

    def linux_mmio():
        return LinuxMMIO(
            [MMIOAperture(4096, frozenset({0}), frozenset({4}))],
            device=str(fixture), owner_lock=str(lock_file))

    def call_cli(action, path=lock_file):
        return subprocess.run([str(binary), action, str(path)],
                              capture_output=True, text=True,
                              timeout=5, check=False)

    # Python owns the advisory lock; independent C process must fail.
    with linux_mmio():
        denied = call_cli("try")
        assert denied.returncode == 8, denied.stdout + denied.stderr
        assert "LOCK_BUSY_OR_DENIED" in denied.stdout
    # A production build (without the Host-only compile flag) must reject
    # an arbitrary lock pathname BEFORE it can open or create that file.
    prod = tmp_path / "production-lock-path-negative"
    prod_cmd = [arg for arg in compile_args
                if arg != "-DPLASMA_SWD_HOST_TEST=1"]
    prod_cmd[-1] = str(prod)
    prod_compiled = subprocess.run(
        prod_cmd, text=True, capture_output=True, timeout=30, check=False)
    assert prod_compiled.returncode == 0, (
        prod_compiled.stdout + prod_compiled.stderr)
    rejected = subprocess.run(
        [str(prod), "try", str(tmp_path / "arbitrary-other-lock")],
        capture_output=True, text=True, timeout=5, check=False)
    assert rejected.returncode == 8
    assert not (tmp_path / "arbitrary-other-lock").exists()
    granted = call_cli("try")
    assert granted.returncode == 0, granted.stdout + granted.stderr

    # C process owns the exact same lock; Python must not open a backend.
    holder = subprocess.Popen(
        [str(binary), "hold", str(lock_file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "LOCK_HELD"
        with pytest.raises(MMIOError, match="owned by another"):
            with linux_mmio():
                pass
    finally:
        if holder.stdin:
            holder.stdin.write("\n")
            holder.stdin.flush()
            holder.stdin.close()
        assert holder.wait(timeout=5) == 0
        if holder.stdout:
            holder.stdout.close()
        if holder.stderr:
            holder.stderr.close()
    with linux_mmio():
        pass

    # Symlinks never redirect the C owner lock, including to a fake file.
    link = tmp_path / "redirected-lock"
    link.symlink_to(lock_file)
    assert call_cli("try", link).returncode == 8


def test_sigkill_releases_site_lock_but_does_not_resolve_pending_write(tmp_path):
    """A killed owner loses flock; lock acquisition is not recovery proof.

    The pending marker is a Host-only stand-in for an accepted SWD command.
    It is deliberately outside the C owner's memory, so this test cannot
    mistake a new process or a new lock epoch for command completion.
    """
    cc = shutil.which("cc")
    assert cc, "Host C compiler required"
    binary = tmp_path / "site-lock-cli"
    built = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-O2", "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
         str(SRC / "plasma_swd_owner_lock.c"),
         str(SRC / "tests/test_plasma_swd_owner_lock_cli.c"),
         "-o", str(binary)],
        capture_output=True, text=True, timeout=30, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    fence = tmp_path / "plasma-mmio.lock"
    pending = tmp_path / "synthetic-unknown-completion"
    owner = subprocess.Popen(
        [str(binary), "hold", str(fence), "1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == "LOCK_HELD"
        pending.write_text("site=1;dut-write=possibly-accepted;completion=unknown\n")
        denied = subprocess.run(
            [str(binary), "try", str(fence), "1"],
            capture_output=True, text=True, timeout=5, check=False)
        assert denied.returncode == 8
        reload_denied = subprocess.run(
            [str(binary), "try", str(fence)],
            capture_output=True, text=True, timeout=5, check=False)
        assert reload_denied.returncode == 8
        owner.kill()  # SIGKILL: no C cleanup, unbind, FIFO drain or lease retire.
        assert owner.wait(timeout=5) < 0
        acquired = subprocess.run(
            [str(binary), "try", str(fence), "1"],
            capture_output=True, text=True, timeout=5, check=False)
        assert acquired.returncode == 0, acquired.stdout + acquired.stderr
        reload_acquired = subprocess.run(
            [str(binary), "try", str(fence)],
            capture_output=True, text=True, timeout=5, check=False)
        assert reload_acquired.returncode == 0
        assert pending.read_text().endswith("completion=unknown\n")
        # A production owner must not infer a safe DUT write replay from
        # acquired.returncode == 0. No persistent admission protocol exists.
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=5)
        for stream in (owner.stdin, owner.stdout, owner.stderr):
            if stream is not None:
                stream.close()


def test_c_lock_bound_lease_is_non_optional():
    header = (SRC / "plasma_swd_lease_word_port.h").read_text()
    impl = (SRC / "plasma_swd_lease_word_port.c").read_text()
    lock = (SRC / "plasma_swd_owner_lock.h").read_text()
    assert '"/run/lock/plasma-mmio.lock"' in lock
    assert "plasma_swd_owner_lock_valid" in impl
    assert "owner_lock_epoch" in header and "owner_lock_epoch" in impl
    assert "plasma_swd_owner_lock_acquire" in lock
    assert "plasma_swd_owner_lock_release" in lock


def test_two_level_ppu_fence_and_per_site_exclusion_host_only(tmp_path):
    """Actual Linux cross-process lock model; fake sparse regular file only."""
    from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOError
    from plasma_interfaces.swd_native_linux_mmio import swd_site_aperture
    from plasma_interfaces.swd_site import SITE_BASES

    cc = shutil.which("cc")
    binary = tmp_path / "site-lock-cli"
    build = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-O2", "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
         str(SRC / "plasma_swd_owner_lock.c"),
         str(SRC / "tests/test_plasma_swd_owner_lock_cli.c"),
         "-o", str(binary)],
        capture_output=True, text=True, timeout=30, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    fence = tmp_path / "plasma-mmio.lock"
    fake = tmp_path / "fake-sparse"
    with fake.open("wb") as handle:
        handle.truncate(SITE_BASES[2] + 4096)

    def python_site(site):
        return LinuxMMIO(
            [swd_site_aperture(site)], device=str(fake),
            owner_lock=str(fence), site_owner=site)

    def c_call(mode, site=None):
        argv = [str(binary), mode, str(fence)]
        if site is not None:
            argv.append(str(site))
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=5, check=False)

    # Both Sites are active concurrently; Root/global EX must reject.
    with python_site(1), python_site(2):
        assert c_call("try", 1).returncode == 8
        assert c_call("try", 2).returncode == 8
        assert c_call("try").returncode == 8
        with pytest.raises(MMIOError, match="Site owned"):
            with python_site(1):
                pass
    assert c_call("try").returncode == 0

    # C Site1 and Python Site2, in different real processes.
    child = subprocess.Popen(
        [str(binary), "hold", str(fence), "1"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "LOCK_HELD"
        with python_site(2) as second:
            with second.claim_site(2, SITE_BASES[2]) as lease:
                assert lease.read32(SITE_BASES[2]) == 0
                assert c_call("try", 2).returncode == 8
                assert c_call("try").returncode == 8
            with pytest.raises(MMIOError, match="Site owned"):
                with python_site(1):
                    pass
    finally:
        if child.stdin:
            child.stdin.write("\n")
            child.stdin.flush()
            child.stdin.close()
        assert child.wait(timeout=5) == 0
        if child.stdout:
            child.stdout.close()
        if child.stderr:
            child.stderr.close()

    # A PPU exclusive Reload fence bars BOTH Sites; no admission ordering
    # deadlock because lock acquisitions are always PPU then Site.
    reload_owner = subprocess.Popen(
        [str(binary), "hold", str(fence)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert reload_owner.stdout is not None
        assert reload_owner.stdout.readline().strip() == "LOCK_HELD"
        for site in (1, 2):
            assert c_call("try", site).returncode == 8
            with pytest.raises(MMIOError, match="MMIO owned"):
                with python_site(site):
                    pass
    finally:
        if reload_owner.stdin:
            reload_owner.stdin.write("\n")
            reload_owner.stdin.flush()
            reload_owner.stdin.close()
        assert reload_owner.wait(timeout=5) == 0
        if reload_owner.stdout:
            reload_owner.stdout.close()
        if reload_owner.stderr:
            reload_owner.stderr.close()
    with python_site(1), python_site(2):
        pass


def test_additive_root_reload_fence_is_not_a_root_guard_replacement():
    """Source guard only: physical Root provenance remains untested."""
    from pl.hil import fpga_image_guard as guard
    import inspect

    root = inspect.getsource(guard.RootZ2TargetPort.exclusive)
    assert "GLOBAL_LOCK" in root and "PPU_RELOAD_FENCE" in root
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in root
    assert "GLOBAL_FPGA_LOCK_UNTRUSTED" in root
    assert "PPU_RELOAD_FENCE_UNTRUSTED" in root
    assert str(guard.PPU_RELOAD_FENCE) == "/run/lock/plasma-mmio.lock"


def test_root_guard_reload_fence_blocks_site_without_loading_fpga(tmp_path, monkeypatch):
    """Actual RootZ2TargetPort.exclusive() flock protocol, Host-only Mock.

    Root identity and path provenance are mocked ONLY in this test;
    kernel flock behavior and competing Python Site lease are real.
    Neither FPGA Manager nor real /dev/mem is ever opened.
    """
    import os
    from types import SimpleNamespace
    from pl.hil import fpga_image_guard as guard
    from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOError
    from plasma_interfaces.swd_native_linux_mmio import swd_site_aperture
    from plasma_interfaces.swd_site import SITE_BASES

    owner_dir = tmp_path / "protected-root-fixture"
    owner_dir.mkdir(mode=0o700)
    fence = tmp_path / "plasma-mmio.lock"
    mmio_fixture = tmp_path / "sparse-fake-image"
    with mmio_fixture.open("wb") as handle:
        handle.truncate(SITE_BASES[2] + 4096)

    def site(site_id):
        return LinuxMMIO(
            (swd_site_aperture(site_id),), device=str(mmio_fixture),
            owner_lock=str(fence), site_owner=site_id)

    real_fstat = os.fstat

    def mock_root_owner_stat(fd):
        st = real_fstat(fd)
        return SimpleNamespace(st_mode=st.st_mode, st_uid=0,
                               st_nlink=st.st_nlink)

    with monkeypatch.context() as patch:
        patch.setattr(guard, "OWNER_DIR", owner_dir)
        patch.setattr(guard, "GLOBAL_LOCK", owner_dir / "supervisor.lock")
        patch.setattr(guard, "PPU_RELOAD_FENCE", fence)
        patch.setattr(guard, "protected", lambda *args, **kwargs: None)
        patch.setattr(guard.os, "geteuid", lambda: 0)
        patch.setattr(guard.os, "fstat", mock_root_owner_stat)
        port = guard.RootZ2TargetPort(release=object())

        with site(1):
            # Real Root reload path MUST be denied by a Site SH fence.
            with pytest.raises(BlockingIOError):
                with port.exclusive():
                    raise AssertionError("Root wrongly entered live reload")
        with port.exclusive():
            # Root is protected by old supervisor EX and the new PPU EX.
            assert port._locked
            for site_id in (1, 2):
                with pytest.raises(MMIOError, match="MMIO owned"):
                    with site(site_id):
                        raise AssertionError("Site started during Root operation")
        with site(1), site(2):
            pass


# --- WP-07: concurrent Site admission (ADR-0007), Host-only --------------------
# Real kernel flock on temp files; Root identity (uid 0) is mocked ONLY here.
# Site owners are LinuxMMIO(site_owner=N), the same fence SH + Site EX
# protocol as the native plasma_swd ps_owner. No FPGA, /dev/mem or DUT.

def _wp07_root(tmp_path, monkeypatch, *, wait_s=0.3):
    import os
    from types import SimpleNamespace
    from pl.hil import fpga_image_guard as guard
    from plasma_interfaces.linux_mmio import LinuxMMIO
    from plasma_interfaces.swd_native_linux_mmio import swd_site_aperture
    from plasma_interfaces.swd_site import SITE_BASES

    owner_dir = tmp_path / "owner"
    owner_dir.mkdir(mode=0o700)
    fence = tmp_path / "plasma-mmio.lock"
    fake_mem = tmp_path / "sparse-fake-image"
    with fake_mem.open("wb") as handle:
        handle.truncate(SITE_BASES[2] + 4096)
    real_fstat, real_lstat = os.fstat, os.lstat

    def as_root(info):
        return SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_nlink=info.st_nlink,
                               st_size=info.st_size, st_dev=info.st_dev, st_ino=info.st_ino)

    monkeypatch.setattr(guard, "OWNER_DIR", owner_dir)
    monkeypatch.setattr(guard, "GLOBAL_LOCK", owner_dir / "supervisor.lock")
    monkeypatch.setattr(guard, "PPU_RELOAD_FENCE", fence)
    monkeypatch.setattr(guard, "SITE_ADMISSION_SUPERVISOR_WAIT_S", wait_s)
    monkeypatch.setattr(guard, "protected", lambda *args, **kwargs: None)
    monkeypatch.setattr(guard.os, "geteuid", lambda: 0)
    monkeypatch.setattr(guard.os, "fstat", lambda fd: as_root(real_fstat(fd)))
    monkeypatch.setattr(guard.os, "lstat", lambda p: as_root(real_lstat(p)))
    release = SimpleNamespace(site_bitmap=3, axi_base=0x43C01000, axi_bytes=0x2000,
                              owner_base=0x43C00000, owner_bytes=0x10000)

    def site_owner(site_id):
        return LinuxMMIO((swd_site_aperture(site_id),), device=str(fake_mem),
                         owner_lock=str(fence), site_owner=site_id)

    def record(site_id, *, boot="boot-a", session="fpga-s1", expires=2**40):
        path = owner_dir / f"swd-site{site_id}-admission"
        path.write_text(f"site_id={site_id}\nboot_id={boot}\n"
                        f"root_image_session_id={session}\nrecord_expires_epoch={expires}\n")
        path.chmod(0o600)
        return path

    return SimpleNamespace(guard=guard, release=release, fence=fence,
                           site_owner=site_owner, record=record,
                           port=lambda: guard.RootZ2TargetPort(release=release))


def test_wp07_other_site_running_sh_admits_this_site_sh(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    for running, admitting in ((1, 2), (2, 1)):
        with r.site_owner(running):
            with r.port().exclusive(site=admitting) as port:
                assert port._locked and port._reload_fence_fd is None
                with pytest.raises(r.guard.TargetSafetyDenied,
                                   match="ROOT_RELOAD_FENCE_NOT_HELD"):
                    port.inherited_reload_fence()  # identity child stays EX-only
            # After admission, this Site's own native owner can attach SH/EX.
            with r.site_owner(admitting):
                pass


def test_wp07_same_site_second_owner_denied(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    with r.site_owner(1):
        with pytest.raises(r.guard.TargetSafetyDenied, match="SITE_OWNER_PRESENT"):
            with r.port().exclusive(site=1):
                raise AssertionError("second Site 1 owner admitted")
    # Admitted but not yet attached: the record reserves the Site.
    r.record(2)
    with pytest.raises(r.guard.TargetSafetyDenied, match="SITE_ADMISSION_RECORD_PRESENT"):
        with r.port().exclusive(site=2):
            raise AssertionError("Site 2 admitted twice")
    with r.port().exclusive(site=1):
        pass


def test_wp07_reload_ex_denied_while_any_site_active_or_admitted(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    for site_id in (1, 2):
        with r.site_owner(site_id):
            with pytest.raises(BlockingIOError):
                with r.port().exclusive():
                    raise AssertionError("reload entered during a live Site")
    # Admission-to-attach window: no owner holds a lock yet, only the record.
    path = r.record(2)
    with pytest.raises(r.guard.TargetSafetyDenied, match="SITE_ADMISSION_RECORD_PRESENT"):
        with r.port().exclusive():
            raise AssertionError("reload entered between admission and attach")
    path.unlink()
    with r.port().exclusive() as port:
        assert port.inherited_reload_fence() >= 3


def test_wp07_site_admission_denied_while_reload_ex_active(tmp_path, monkeypatch):
    import fcntl, os
    r = _wp07_root(tmp_path, monkeypatch)
    with r.port().exclusive():
        for site_id in (1, 2):
            with pytest.raises(r.guard.TargetSafetyDenied, match="ROOT_SUPERVISOR_BUSY"):
                with r.port().exclusive(site=site_id):
                    raise AssertionError("Site admitted during reload")
    # Fence EX held by a reload path without the supervisor lock: still denied.
    fd = os.open(r.fence, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with pytest.raises(r.guard.TargetSafetyDenied, match="PPU_RELOAD_IN_PROGRESS"):
            with r.port().exclusive(site=1):
                raise AssertionError("Site admitted under fence EX")
    finally:
        os.close(fd)


def test_wp07_distinct_site_admissions_overlap_while_reload_stays_exclusive(tmp_path, monkeypatch):
    """Real host flock: Site 2 enters while Site 1 still holds Root SH."""
    import threading
    r = _wp07_root(tmp_path, monkeypatch, wait_s=1.0)
    first_inside, release_first = threading.Event(), threading.Event()
    second_inside, results = threading.Event(), {}

    def first():
        with r.port().exclusive(site=1):
            results[1] = "ENTERED"
            first_inside.set()
            release_first.wait(5)

    def second():
        if not first_inside.wait(5):
            results[2] = "FIRST_NOT_READY"
            return
        with r.port().exclusive(site=2):
            results[2] = "ENTERED"
            second_inside.set()
            # Both site admissions exist: a concurrent Root reload is denied.
            with pytest.raises(BlockingIOError):
                with r.port().exclusive():
                    raise AssertionError("reload bypassed two Site admissions")
            results["reload"] = "DENIED"

    a, b = threading.Thread(target=first), threading.Thread(target=second)
    a.start(); b.start()
    try:
        assert first_inside.wait(5)
        assert second_inside.wait(2), "Site 2 was serialized behind Site 1"
    finally:
        release_first.set()
        a.join(10); b.join(10)
    assert not a.is_alive() and not b.is_alive()
    assert results == {1: "ENTERED", 2: "ENTERED", "reload": "DENIED"}


def test_wp07_same_site_root_admissions_do_not_overlap(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    with r.port().exclusive(site=1):
        with pytest.raises(r.guard.TargetSafetyDenied, match="SITE_OWNER_PRESENT"):
            with r.port().exclusive(site=1):
                raise AssertionError("same Site acquired twice")



def _wp07_proc(tmp_path, r, pids):
    """Synthetic /proc: {pid: (fd_targets, [(offset, size, device)])} plus locks."""
    import os
    proc = tmp_path / "proc"
    proc.mkdir()
    for pid, (fds, maps) in pids.items():
        (proc / pid / "fd").mkdir(parents=True)
        for n, target in enumerate(fds, start=3):
            os.symlink(target, proc / pid / "fd" / str(n))
        (proc / pid / "maps").write_text("".join(
            f"b6f00000-{0xb6f00000 + size:08x} rw-s {offset:08x} 00:06 1 {device}\n"
            for offset, size, device in maps))
    return proc


def _wp07_locks(proc, entries):
    import os
    lines = []
    for n, (mode, pid, path) in enumerate(entries, start=1):
        info = os.stat(path)
        lines.append(f"{n}: FLOCK  ADVISORY  {mode} {pid} "
                     f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino} 0 EOF")
    (proc / "locks").write_text("\n".join(lines) + "\n")


def test_wp07_census_admits_proven_other_site_owner_only(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    g = r.guard
    site2_lock = g.site_lock_path(2)
    site2_lock.touch(); r.fence.touch()
    own_page = [(0x43C02000, 0x1000, "/dev/mem")]
    proc = _wp07_proc(tmp_path, r, {
        "100": (["/dev/mem"], own_page),                                 # proven Site 2 owner
        "200": (["/dev/mem"], own_page),                                 # named "openocd", no locks
        "300": (["/dev/null"], []),                                      # unrelated
    })
    _wp07_locks(proc, [("WRITE", "100", site2_lock), ("READ", "100", r.fence)])
    r.record(2)
    bound = dict(release=r.release, admitting_site=1, boot_id="boot-a",
                 session_id="fpga-s1", procroot=proc)
    assert g.cooperating_site_owners(**bound) == {"100": 2}
    complete, conflicts = g.scan_proc_consumers(
        procroot=proc, release=r.release, cooperating=lambda: g.cooperating_site_owners(**bound))
    # The proven owner passes; a PID with no lock evidence is still a conflict.
    assert complete is True and conflicts == ["200"]

    # Without exemption (legacy census) both /dev/mem users conflict.
    assert g.scan_proc_consumers(procroot=proc, release=r.release)[1] == ["100", "200"]


@pytest.mark.parametrize("case", [
    "session_mismatch", "boot_mismatch", "expired", "no_record", "wrong_site_record",
    "lock_by_other_pid", "no_fence_read", "admitting_own_site"])
def test_wp07_census_unverified_owner_stays_conflict(tmp_path, monkeypatch, case):
    r = _wp07_root(tmp_path, monkeypatch)
    g = r.guard
    site2_lock = g.site_lock_path(2)
    site2_lock.touch(); r.fence.touch()
    proc = _wp07_proc(tmp_path, r, {"100": (["/dev/mem"], [(0x43C02000, 0x1000, "/dev/mem")])})
    locks = [("WRITE", "100", site2_lock), ("READ", "100", r.fence)]
    record = {}
    if case == "session_mismatch": record = {"session": "fpga-other"}
    if case == "boot_mismatch": record = {"boot": "boot-b"}
    if case == "expired": record = {"expires": 1}
    if case == "lock_by_other_pid": locks[0] = ("WRITE", "999", site2_lock)
    if case == "no_fence_read": locks = locks[:1]
    _wp07_locks(proc, locks)
    if case == "wrong_site_record":
        r.record(2).write_text("site_id=1\nboot_id=boot-a\nroot_image_session_id=fpga-s1\n"
                               "record_expires_epoch=1099511627776\n")
    elif case != "no_record":
        r.record(2, **record)
    owners = g.cooperating_site_owners(
        release=r.release, admitting_site=2 if case == "admitting_own_site" else 1,
        boot_id="boot-a", session_id="fpga-s1", procroot=proc)
    assert owners == {}
    assert g.scan_proc_consumers(procroot=proc, release=r.release,
                                 cooperating=lambda: owners)[1] == ["100"]


@pytest.mark.parametrize("fds,maps", [
    (["/dev/mem"], [(0x43C01000, 0x1000, "/dev/mem")]),            # maps the admitting Site's page
    (["/dev/mem"], [(0x43C02000, 0x2000, "/dev/mem")]),            # spills past its own page
    (["/dev/mem"], [(0x43C00000, 0x1000, "/dev/mem")]),            # PPU owner/ABI page
    (["/dev/mem", "/dev/uio0"], [(0x43C02000, 0x1000, "/dev/mem")]),
    (["/dev/mem", "/dev/xdevcfg"], [(0x43C02000, 0x1000, "/dev/mem")]),
])
def test_wp07_proven_owner_cross_site_or_fpga_resource_still_conflicts(
        tmp_path, monkeypatch, fds, maps):
    r = _wp07_root(tmp_path, monkeypatch)
    g = r.guard
    proc = _wp07_proc(tmp_path, r, {"100": (fds, maps)})
    assert g.scan_proc_consumers(procroot=proc, release=r.release,
                                 cooperating=lambda: {"100": 2})[1] == ["100"]



def test_wp07_owner_attaching_during_the_census_is_proven_at_observation(tmp_path, monkeypatch):
    """Z2 step 6 (2026-11-15): Site 2's OpenOCD attached after a pre-scan
    snapshot of /proc/locks, so Site 1's census saw /dev/mem without proof."""
    import os
    r = _wp07_root(tmp_path, monkeypatch)
    g = r.guard
    site2_lock = g.site_lock_path(2)
    site2_lock.touch(); r.fence.touch()
    proc = _wp07_proc(tmp_path, r, {"100": (["/dev/mem"], [(0x43C02000, 0x1000, "/dev/mem")])})
    _wp07_locks(proc, [])  # nothing locked when the census starts
    r.record(2)
    bound = dict(release=r.release, admitting_site=1, boot_id="boot-a",
                 session_id="fpga-s1", procroot=proc)
    real_readlink = os.readlink

    def attach_then_read(path):
        # The native owner locks BEFORE opening /dev/mem: by the time its fd is
        # observed, its Site lock and fence SH are held.
        if "/100/fd/" in str(path):
            _wp07_locks(proc, [("WRITE", "100", site2_lock), ("READ", "100", r.fence)])
        return real_readlink(path)

    monkeypatch.setattr(g.os, "readlink", attach_then_read)
    stale = g.cooperating_site_owners(**bound)
    assert stale == {}  # what a pre-scan snapshot would have used
    _wp07_locks(proc, [])
    assert g.scan_proc_consumers(procroot=proc, release=r.release,
                                 cooperating=lambda: g.cooperating_site_owners(**bound)) == (True, [])
    # The pre-fix snapshot semantics deny the same, legitimate owner.
    _wp07_locks(proc, [])
    assert g.scan_proc_consumers(procroot=proc, release=r.release,
                                 cooperating=lambda: stale)[1] == ["100"]

def test_wp07_unbound_site_admission_exempts_nothing(tmp_path, monkeypatch):
    r = _wp07_root(tmp_path, monkeypatch)
    seen = {}
    monkeypatch.setattr(r.guard, "read_live_z2_facts",
                        lambda **kw: seen.setdefault("cooperating", kw.get("cooperating")))
    with r.port().exclusive(site=1) as port:
        port.current_facts()
        assert callable(seen["cooperating"]) and seen["cooperating"]() == {}
        with pytest.raises(r.guard.TargetSafetyDenied, match="SITE_SESSION_BINDING_INVALID"):
            port.bind_site_session(boot_id="", session_id="fpga-s1")
    seen.clear()
    with r.port().exclusive() as port:  # reload: no Site exemption at all
        port.current_facts()
        assert seen["cooperating"] is None


def test_native_v5_word_access_c_compilation_and_owner_fail_closed(tmp_path):
    """C word MMIO driver from PR #1199 technique, v5/2-Site synthetic only.

    No /dev/mem open, real mapping, Root privilege, SWCLK pin or DUT.
    """
    cc = shutil.which("cc")
    assert cc, "GitHub-hosted C compiler required"
    exe = tmp_path / "native-v5-words-host-only"
    args = [
        cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
        str(SRC / "plasma_swd_fifo_core.c"),
        str(SRC / "plasma_swd_native_words.c"),
        str(SRC / "plasma_swd_lease_word_port.c"),
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "tests/test_plasma_swd_native_words.c"),
        "-o", str(exe),
    ]
    built = subprocess.run(args, capture_output=True, text=True,
                           timeout=30, check=False)
    assert built.returncode == 0, built.stdout + built.stderr
    verified = subprocess.run([str(exe)], capture_output=True, text=True,
                              timeout=15, check=False)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "PLASMA_NATIVE_V5_WORDS_HOST_ONLY_PASS" in verified.stdout


def test_native_v5_mmio_is_volatile_words_not_legacy_bitbang():
    c = (SRC / "plasma_swd_native_words.c").read_text()
    h = (SRC / "plasma_swd_native_words.h").read_text()
    assert "volatile uint32_t" in h
    assert "__ARM_ARCH_7A__" in c and '"dmb sy"' in c
    assert "atomic_signal_fence" in c
    assert "plasma_swd_owner_lock_valid" in c
    assert "lease_generation" in c
    assert "authorize(n->authority_ctx" in c
    for forbidden in (
        "/dev/mem\"", "mmap(", "open(", "socket(", "remote_bitbang",
        "plasma_rbb_exchange", "bluepill_wordport_bridge", "MODE_DEBUG",
    ):
        assert forbidden not in c


def test_ps_native_fd_mapping_host_only_sparse_file_and_revocation(tmp_path):
    """Real native C mmap/munmap and FIFO against regular-file fake AXI.

    Does NOT touch /dev/mem, FPGA Manager, Z2 or DUT. The source is
    compiled with a test-only macro that disallows character devices.
    """
    cc = shutil.which("cc")
    assert cc, "Host compiler required"
    exe = tmp_path / "ps-native-v5-fd-map"
    cmd = [
        cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-pedantic", "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
        str(SRC / "plasma_swd_ps_mapping.c"),
        str(SRC / "plasma_swd_fifo_core.c"),
        str(SRC / "plasma_swd_native_words.c"),
        str(SRC / "plasma_swd_lease_word_port.c"),
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "tests/test_plasma_swd_ps_mapping.c"),
        "-o", str(exe),
    ]
    compile_result = subprocess.run(cmd, text=True, capture_output=True,
                                    timeout=30, check=False)
    assert compile_result.returncode == 0, (
        compile_result.stdout + compile_result.stderr)
    run = subprocess.run([str(exe)], text=True, capture_output=True,
                         timeout=30, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PLASMA_PSNATIVE_MAPPED_FD_HOST_ONLY_PASS" in run.stdout


def test_ps_mapping_requires_external_preopened_fd_and_production_char_device():
    c = (SRC / "plasma_swd_ps_mapping.c").read_text()
    h = (SRC / "plasma_swd_ps_mapping.h").read_text()
    assert "mmap(" in c and "munmap(" in c
    assert "S_ISCHR" in c and "major(st.st_rdev)" in c
    assert "PLASMA_SWD_HOST_TEST" in c
    assert "FD_CLOEXEC" in c and "O_SYNC" in c
    assert "plasma_swd_native_words_ready" in c
    assert "owner->site_id != site_id" in c
    assert "authorize(authority_ctx, site_id, generation)" in c
    assert "preopened_fd" in h
    for forbidden in (
        'open("/dev/mem"', "socket(", "remote_bitbang",
        "MODE_DEBUG", "bluepill_wordport_bridge",
    ):
        assert forbidden not in c


def test_ps_owner_lock_and_loaded_image_host_only(tmp_path):
    """PS-local OpenOCD owner: Site lock + loaded-Image precheck, no per-word file I/O.

    Fixture files stand in for /proc, sysfs, Root journal and /dev/mem.
    Host-only; NOT Z2, FPGA or DUT evidence.
    """
    cc = shutil.which("cc")
    assert cc, "Host C compiler required"
    executable = tmp_path / "ps-owner"
    sources = [
        "plasma_swd_fifo_core.c", "plasma_swd_native_words.c",
        "plasma_swd_owner_lock.c", "plasma_swd_lease_word_port.c",
        "plasma_swd_ps_mapping.c",
        "plasma_swd_openocd5088_callbacks.c",
        "plasma_swd_openocd5088_ps_owner.c",
        "tests/test_plasma_swd_ps_owner.c",
    ]
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2",
         "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
         "-I", str(SRC / "tests/openocd_shim"),
         *[str(SRC / s) for s in sources], "-o", str(executable)],
        capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    done = subprocess.run([str(executable), str(fixtures)], capture_output=True,
                          text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PLASMA_SWD_PS_OWNER_HOST_ONLY_PASS" in done.stdout


def test_ps_owner_production_paths_and_no_host_relaxation():
    src = (SRC / "plasma_swd_openocd5088_ps_owner.c").read_text()
    assert '"/dev/mem"' in src and "O_RDWR | O_SYNC | O_CLOEXEC" in src
    assert "#define TRUSTED_UID 0u" in src
    assert "PLASMA_SWD_MMIO_OWNER_LOCK" in src
    assert "plasma_swd_owner_lock_acquire_site" in src
    assert "/var/lib/plasma-privileged/fpga-deployment-state.json" in src
    # Policy (which Image, electrical conditions) belongs to the caller: the
    # adapter reads neither an admission record nor an attestation.
    for gone in ("swd-site", "electrical", "attestation", "read_live"):
        assert gone not in src
    drv = (SRC / "plasma_swd_openocd5088_driver.c").read_text()
    assert "plasma_swd_ps_owner_attach" in drv
    assert "plasma_swd_ps_owner_safe_off" in drv


def _site_admission_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "plasma_swd_site_admission",
        ROOT / "scripts/z2/plasma_swd_site_admission.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_site_admission_record_fields_are_complete_and_validated():
    """Host-only: the Python Root record writer rejects malformed records."""
    adm = _site_admission_module()
    keys = ["schema", "site_id", "boot_id", "trusted_code_sha256",
            "image_manifest_sha256", "loaded_image_sha256", "image_id",
            "root_image_session_id", "abi_version", "site_bitmap",
            "trusted_code_verified", "manager_operating", "active_image_attested",
            "axi_isolation_proven", "owner_scan_complete",
            "recovery_available", "journal_dev", "journal_ino", "journal_size",
            "journal_mtime_ns", "record_expires_epoch",
            "code_manifest_dev", "code_manifest_ino", "code_manifest_size",
            "code_manifest_mtime_ns"]
    fields = {k: "1" for k in keys}
    fields["schema"] = adm.SCHEMA
    text = adm.render_record(fields)
    assert [line.split("=", 1)[0] for line in text.splitlines()] == keys
    for bad in ({**fields, "boot_id": "a\nx=1"},
                {**fields, "boot_id": ""}, {**fields, "x": "1"},
                {k: v for k, v in fields.items() if k != "site_id"}):
        with pytest.raises(adm.SiteAdmissionDenied):
            adm.render_record(bad)


def test_site_admission_fails_closed_without_root_or_args(capsys):
    import os
    adm = _site_admission_module()
    assert adm.main([]) == 2
    assert adm.main(["admit", "3"]) == 2
    assert adm.main(["load", "1"]) == 2
    if os.geteuid() != 0:
        assert adm.main(["admit", "1"]) == 1
        out = capsys.readouterr().out
        assert '"result": "DENIED"' in out and "ROOT_REQUIRED" in out


def test_site_admission_protected_tree_negative(tmp_path, monkeypatch):
    adm = _site_admission_module()
    tree = tmp_path / "tree"
    tree.mkdir()
    # Missing Linux-protected installed source fails closed, no repeated hash.
    monkeypatch.setattr(adm, "PROTECTED_ROOT", tree)
    # New source-closure issuer must fail before importing any untrusted code.
    with pytest.raises((adm.SiteAdmissionDenied, OSError)):
        adm.verify_protected_tree(tree)


def test_site_admission_never_loads_fpga_or_writes_journal():
    text = (ROOT / "scripts/z2/plasma_swd_site_admission.py").read_text()
    for forbidden in ("manager_write", "write_state(", "root.run(",
                      "LinuxMMIO", "/dev/mem", "record_json"):
        assert forbidden not in text
    assert "require_mmio=True" in text and "port.exclusive(site=site)" in text
    assert '"voltage_source": "NOT_MEASURED"' in text
