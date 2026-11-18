#!/usr/bin/env python3
"""Run one local, reviewed Python file on Z2 as root via the existing pinned
SSH/sudo helper. Usage: z2run.py <script.py> [timeout_s]
Credentials stay in process memory; output is sanitized by the helper."""
import importlib.util, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("wp", REPO / "scripts/plasma_wordport_program.py")
wp = importlib.util.module_from_spec(spec); sys.modules["wp"] = wp; spec.loader.exec_module(wp)

code = Path(sys.argv[1]).read_text()
timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 120
creds, hosts = wp.z2_login_credentials(Path.home())
if creds["ssh_host"] != "192.168.2.99":
    raise SystemExit("UNEXPECTED_HOST")
rc, out = wp.password_ssh_z2(["python3", "-I", "-B", "-c", code], creds, hosts, timeout=timeout)
print(out[-60000:])
print(f"Z2RUN_EXIT={rc}")
sys.exit(rc)
