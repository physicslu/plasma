from __future__ import annotations

from .programming import ProgrammingOperationHandler


class STM32F103Handler(ProgrammingOperationHandler):
    """Legacy compatibility name for the pre-IC-Support STM32F103 handler.

    New execution routing must select a handler from ResolvedICSupport rather
    than constructing this class unconditionally for every Site.
    """

    TARGET_NAME = "STM32F103C8T6"
