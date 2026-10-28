import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time

mode = sys.argv[1]
assert mode in ('program_v01', 'readback_v01', 'readback_v01_tail', 'readback_v01_600', 'reset_v01')
root = Path('/root/plasma-path2-approved')
bundle = Path('/home/xilinx/plasma-native-c-wordport-1199')
socket_dir = Path('/run/plasma-native-wordport-1199-' + mode)
socket = socket_dir / 'swd.sock'
image = Path('/home/xilinx/plasma-bluepill-ab-20261028/plasma-blue-pill-cdc.bin')
assert image.is_file() and image.stat().st_size == 18768
assert hashlib.sha256(image.read_bytes()).hexdigest() == '8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
pin = (root / '.plasma-path2-source-commit').read_text().strip()
state = json.loads((root / '.plasma-fpga-image-deployment-state.json').read_text())
manifest_path = Path('/lib/firmware/plasma-image-manifest.json')
manifest = json.loads(manifest_path.read_text())
manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
barrier = bundle / 'software/python/native/libplasma_mmio_barrier.so'
barrier_sha = hashlib.sha256(barrier.read_bytes()).hexdigest()
native = bundle / 'libplasma_wordport_armv7.so'
native_sha = '66261cef851c9777469b393b7539c5b0f8c2b039a032f1a5b4cbf9e93460e447'
assert hashlib.sha256(native.read_bytes()).hexdigest() == native_sha, 'NATIVE_SHA_CHANGED'
assert hashlib.sha256((bundle / 'scripts/bluepill-wordport-session.py').read_bytes()).hexdigest() == 'ce325d8c965f36208036158a2bce810f445f4ff053415f96e62fba156ff41650', 'SESSION_SHA_CHANGED'
assert hashlib.sha256((bundle / 'software/python/plasma_interfaces/native_bluepill_word_port.py').read_bytes()).hexdigest() == '57dfad519993910ae04e1b05b1592b06d9db856b665a50bd81dd47dc6154b3ef', 'PY_MODULE_SHA_CHANGED'
assert boot == '4cefdc0c-f586-4d19-b126-1d8e1108c8f1', 'BOOT_CHANGED'
assert pin == '55f6db3bc5fa866135e5a9070175928d044e53ce', 'PIN_CHANGED'
subprocess.run(['sha256sum', '--check', '--status', '.plasma-path2-source-sha256'],
               cwd=root, check=True, timeout=15)
assert manifest_sha == '5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98', 'MANIFEST_CHANGED'
assert hashlib.sha256((Path('/lib/firmware') / manifest['firmware_name']).read_bytes()).hexdigest() == manifest['firmware_sha256'], 'BIN_CHANGED'
assert hashlib.sha256((Path('/lib/firmware') / manifest['recovery_name']).read_bytes()).hexdigest() == manifest['recovery_sha256'], 'GOLDEN_CHANGED'
assert state['firmware_sha256'] == manifest['firmware_sha256'], 'IMAGE_CHANGED'
assert state['status'] == 'IMAGE' and state['boot_id'] == boot and state['test_count'] >= 3, 'CHECKPOINT_CHANGED'
assert state['manifest_sha256'] == manifest_sha and state['image'] == manifest['firmware_name'], 'IMAGE_NOT_HELD'
assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating', 'MANAGER_NOT_OPERATING'
assert not socket_dir.exists(), 'SOCKET_DIR_EXISTS'
for node in ('/dev/mem', '/dev/uio1'):
    p = subprocess.run(['fuser', '-s', node], capture_output=True, timeout=4)
    assert p.returncode == 1, 'MMIO_DEVICE_BUSY_OR_UNKNOWN'
for proc in Path('/proc').iterdir():
    if not proc.name.isdecimal():
        continue
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    assert not (args and (Path(args[0].decode(errors='replace')).name == 'openocd' or
                            any(a.startswith(b'/') and b'/bluepill-wordport-session' in a and a.endswith(b'.py') for a in args))), 'EXISTING_SWD_OWNER'
output = bundle / ('readback-v01-native-600.bin' if mode == 'readback_v01_600' else 'readback-v01-native-tail.bin' if mode == 'readback_v01_tail' else 'readback-v01-native.bin')
if mode == 'readback_v01':
    assert not output.exists(), 'READBACK_ALREADY_EXISTS'
if mode == 'readback_v01_600':
    assert not output.exists(), 'READBACK_ALREADY_EXISTS'
if mode == 'readback_v01_tail':
    first = bundle / 'readback-v01-native.bin'
    assert first.is_file() and first.stat().st_size == 12288 and first.read_bytes() == image.read_bytes()[:12288], 'PREFIX_NOT_VERIFIED'
    assert not output.exists(), 'TAIL_ALREADY_EXISTS'
if mode == 'reset_v01':
    first = bundle / 'readback-v01-native.bin'
    tail = bundle / 'readback-v01-native-tail.bin'
    assert first.is_file() and tail.is_file() and first.read_bytes() + tail.read_bytes() == image.read_bytes(), 'READBACK_NOT_VERIFIED'
socket_dir.mkdir(mode=0o700)
py = '/opt/plasma/python/3.12.13/bin/python3'
bridge_cmd = [py, '-I', '-B', str(bundle / 'scripts/bluepill-wordport-session.py'),
              '--root-source-sha', pin, '--boot-id', boot,
              '--barrier', str(barrier), '--barrier-sha256', barrier_sha,
              '--native', str(native), '--native-sha256', native_sha,
              '--socket', str(socket), '--owner-attested']
openocd = '/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/bin/openocd'
scripts = '/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/share/openocd/scripts'
prefix = ('gdb_port disabled; tcl_port disabled; telnet_port disabled; '
          'adapter driver remote_bitbang; remote_bitbang host ' + str(socket) + '; '
          'remote_bitbang port 0; transport select swd; adapter speed 100; '
          'source [find target/stm32f1x.cfg]; init; halt; flash probe 0; ')
if mode == 'program_v01':
    action = f'flash erase_address 0x08000000 0x4c00; flash write_image {image} 0x08000000 bin; shutdown'
elif mode in ('readback_v01', 'readback_v01_600'):
    action = f'dump_image {output} 0x08000000 18768; ' + ('resume; ' if mode == 'readback_v01_600' else '') + 'shutdown'
elif mode == 'readback_v01_tail':
    action = f'dump_image {output} 0x08003000 6480; shutdown'
else:
    action = 'reset run; shutdown'
config = prefix + action
bridge = subprocess.Popen(bridge_cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=True)
open_result = None
bridge_out = bridge_err = ''
try:
    deadline = time.monotonic() + 8
    while not socket.is_socket():
        if bridge.poll() is not None:
            raise RuntimeError('BRIDGE_EXITED_BEFORE_SOCKET')
        if time.monotonic() > deadline:
            raise RuntimeError('BRIDGE_SOCKET_TIMEOUT')
        time.sleep(0.05)
    open_result = subprocess.run([openocd, '-s', scripts, '-c', config],
                                 capture_output=True, text=True, timeout=580 if mode == 'readback_v01_600' else 90)
    bridge_out, bridge_err = bridge.communicate(timeout=4)
finally:
    if bridge.poll() is None:
        bridge.terminate()
        try:
            bridge_out, bridge_err = bridge.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            bridge.kill()
            bridge_out, bridge_err = bridge.communicate(timeout=3)
result = {
    'mode': mode, 'boot_id': boot, 'manifest_sha256': manifest_sha, 'native_sha256': native_sha,
    'barrier_sha256': barrier_sha, 'bridge_exit': bridge.returncode,
    'bridge_stdout': bridge_out, 'bridge_stderr': bridge_err,
    'openocd_exit': open_result.returncode if open_result else None,
    'openocd_log': ((open_result.stdout + open_result.stderr)
                    if open_result else ''),
    'socket_left': socket.exists(),
}
if mode in ('readback_v01', 'readback_v01_tail', 'readback_v01_600'):
    result['bytes'] = output.stat().st_size if output.is_file() else None
    result['sha256'] = hashlib.sha256(output.read_bytes()).hexdigest() if output.is_file() else None
    expected = image.read_bytes()[12288:] if mode == 'readback_v01_tail' else image.read_bytes()
    result['byte_match'] = output.is_file() and output.read_bytes() == expected
    if output.is_file():
        user = pwd.getpwnam('xilinx')
        os.chown(output, user.pw_uid, user.pw_gid)
log = result['openocd_log'].lower()
result['dpidr_observed'] = ('0x1ba01477' in log or '1ba01477' in log)
passed = (result['dpidr_observed'] and result['openocd_exit'] == 0 and
          bridge.returncode == 0 and not result['socket_left'])
if mode in ('readback_v01', 'readback_v01_tail', 'readback_v01_600'):
    passed = passed and result['bytes'] == (6480 if mode == 'readback_v01_tail' else 18768) and result['byte_match']
result['result'] = 'PASS' if passed else 'FAIL'
print(json.dumps(result, sort_keys=True))
if not socket.exists():
    socket_dir.rmdir()
raise SystemExit(0 if passed else 1)
