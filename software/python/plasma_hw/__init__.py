"""PPU-local hardware execution adapters.

This package owns PS/PL transport details. Higher-level Programming Logic must
not depend on raw UIO registers or AXI offsets.
"""

from .pl_loopback import PLLoopbackDevice, UIORegisterIO

__all__ = ["PLLoopbackDevice", "UIORegisterIO"]
