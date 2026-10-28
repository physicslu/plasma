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
    assert "PLASMA_SWD_ABI_V5" in h and "PLASMA_SWD_MAX_QUEUE 16u" in h
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


def test_native_root_observation_is_continuously_compared_host_only(tmp_path):
    """Real C observer ↔ Native MMIO chain, deliberately synthetic Root.

    Real protected Root currently reports active_image_attestation and
    axi_isolation_evidence as UNPROVEN, so no physical admittance is claimed.
    """
    cc = shutil.which("cc")
    assert cc, "GitHub-hosted C compiler required"
    binary = tmp_path / "swd-ps-owner-evidence"
    compile_args = [
        cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-DPLASMA_SWD_HOST_TEST=1", "-I", str(SRC),
        str(SRC / "plasma_swd_owner_evidence.c"),
        str(SRC / "plasma_swd_fifo_core.c"),
        str(SRC / "plasma_swd_native_words.c"),
        str(SRC / "plasma_swd_lease_word_port.c"),
        str(SRC / "plasma_swd_owner_lock.c"),
        str(SRC / "tests/test_plasma_swd_owner_evidence.c"),
        "-o", str(binary),
    ]
    build = subprocess.run(compile_args, capture_output=True, text=True,
                           timeout=30, check=False)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True,
                         timeout=30, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PLASMA_PSNATIVE_LIVE_EVIDENCE_HOST_ONLY_PASS" in run.stdout


def test_native_owner_evidence_never_treats_root_journal_as_loaded_image_proof():
    owner = (SRC / "plasma_swd_owner_evidence.c").read_text()
    contract = (SRC / "plasma_swd_owner_evidence.h").read_text()
    # Existing protected Root journal/session remains only a reference,
    # never a per-Image approval token or independent proof of PL bits.
    assert "root_image_session_id" in contract
    assert "active_image_attested" in owner
    assert "axi_isolation_proven" in owner
    assert "root_source_pinned" in owner
    assert "root_source_commit" in owner
    assert "loaded_image_sha256" in owner
    assert "image_manifest_sha256" in owner
    assert "voltage_qualified" in owner
    assert "plasma_swd_owner_evidence_authorize" in owner
    for prohibited in (
        "mmap(", 'open("/dev/mem"', "socket(", "remote_bitbang",
        "runtime_admitted", "approved-fpga-image.json", "MODE_DEBUG",
    ):
        assert prohibited not in owner
