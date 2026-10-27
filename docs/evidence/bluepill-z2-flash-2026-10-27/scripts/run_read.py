import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root = Path('/root/plasma-path2-approved')
bundle = Path('/opt/plasma/bluepill-direct-20261026')
socket_dir = Path('/run/plasma-bluepill-flash-read-20261027')
socket = socket_dir / 'swd.sock'
page = socket_dir / 'last-page.bin'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
pin = (root / '.plasma-path2-source-commit').read_text().strip()
state = json.loads((root / '.plasma-fpga-image-deployment-state.json').read_text())
manifest_path = Path('/lib/firmware/plasma-image-manifest.json')
manifest = json.loads(manifest_path.read_text())
manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
barrier = bundle / 'software/python/native/libplasma_mmio_barrier.so'
barrier_sha = hashlib.sha256(barrier.read_bytes()).hexdigest()
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
socket_dir.mkdir(mode=0o700)
py = '/opt/plasma/python/3.12.13/bin/python3'
bridge_cmd = [py, '-I', '-B', str(bundle / 'scripts/bluepill-wordport-session.py'),
              '--root-source-sha', pin, '--boot-id', boot,
              '--barrier', str(barrier), '--barrier-sha256', barrier_sha,
              '--socket', str(socket), '--owner-attested']
openocd = '/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/bin/openocd'
scripts = '/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154/share/openocd/scripts'
config = ('gdb_port disabled; tcl_port disabled; telnet_port disabled; '
          'adapter driver remote_bitbang; remote_bitbang host ' + str(socket) + '; '
          'remote_bitbang port 0; transport select swd; adapter speed 100; '
          'source [find target/stm32f1x.cfg]; '
          'init; halt; flash probe 0; '
          'dump_image ' + str(page) + ' 0x0800FC00 0x400; '
          'resume; shutdown')
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
                                 capture_output=True, text=True, timeout=55)
    bridge_out, bridge_err = bridge.communicate(timeout=8)
finally:
    if bridge.poll() is None:
        bridge.terminate()
        try:
            bridge_out, bridge_err = bridge.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            bridge.kill()
            bridge_out, bridge_err = bridge.communicate(timeout=3)
result = {
    'boot_id': boot, 'manifest_sha256': manifest_sha,
    'barrier_sha256': barrier_sha, 'bridge_exit': bridge.returncode,
    'bridge_stdout': bridge_out[-2000:], 'bridge_stderr': bridge_err[-2000:],
    'openocd_exit': open_result.returncode if open_result else None,
    'openocd_log': ((open_result.stdout + open_result.stderr)[-5000:]
                    if open_result else ''),
    'socket_left': socket.exists(),
}
page_bytes = page.read_bytes() if page.is_file() else b''
result['page_size'] = len(page_bytes)
result['page_sha256'] = hashlib.sha256(page_bytes).hexdigest() if page_bytes else None
result['page_all_ff'] = bool(page_bytes) and all(byte == 0xFF for byte in page_bytes)
result['page_base64'] = base64.b64encode(page_bytes).decode('ascii') if page_bytes else None
result['result'] = ('FLASH_READ_COMMAND_EXIT_0' if
                    result['openocd_exit'] == 0 and bridge.returncode == 0 and
                    not result['socket_left'] and len(page_bytes) == 1024 and
                    'flash size = 64 KiB' in result['openocd_log'] and
                    'device id = 0x20036410' in result['openocd_log']
                    else 'FLASH_READ_FAIL')
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result['result'] == 'FLASH_READ_COMMAND_EXIT_0' else 1)
