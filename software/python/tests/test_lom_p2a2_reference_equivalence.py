"""LOM-P2A-2: every P2A-0 reference case against the REAL controller engine.

The reference test module is compiled a second time with its ``m`` bound to
``lom_p2a2_real_engine_shim`` (real ``scripts/ppu_controller.py`` + real
``scripts/ppu_local_enrollment.py`` + real atomic files). Host-only; no SD
card, network, PPU, FPGA or DUT.
"""
from __future__ import annotations

import types
from pathlib import Path

from . import lom_p2a2_real_engine_shim as shim

_SOURCE = Path(__file__).with_name("test_lom_p2a0_enrollment_spec.py")
_module = types.ModuleType(__name__ + "._p2a0_cases")
_module.__file__ = str(_SOURCE)
_code = _SOURCE.read_text(encoding="utf-8").replace(
    "from . import lom_p2a0_reference_model as m",
    "m = __shim__",
)
_module.__dict__["__shim__"] = shim
exec(compile(_code, str(_SOURCE), "exec"), _module.__dict__)

for _name, _value in list(_module.__dict__.items()):
    if _name.startswith("test_"):
        globals()[_name + "__real_engine"] = _value
