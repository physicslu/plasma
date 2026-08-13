from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from plasma_core.models import ExecutionOutput, JobRequest
from plasma_interfaces.base import BaseInterface

StageCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class BaseHandler(ABC):
    def __init__(self, interface: BaseInterface) -> None:
        self.interface = interface

    @abstractmethod
    async def execute(self, request: JobRequest, stage_callback: StageCallback) -> ExecutionOutput:
        raise NotImplementedError
