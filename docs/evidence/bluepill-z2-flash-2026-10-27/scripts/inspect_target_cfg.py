"""Read-only inspection of the installed Z2 OpenOCD STM32F1 target script."""
import hashlib
import json
from pathlib import Path

base = Path('/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154')
target = base / 'share/openocd/scripts/target/stm32f1x.cfg'
print(json.dumps({'target_config_exists': target.is_file(),
                  'target_config_sha256': hashlib.sha256(target.read_bytes()).hexdigest()
                      if target.is_file() else None,
                  'target_config_text': target.read_text() if target.is_file() else None},
                 sort_keys=True))
