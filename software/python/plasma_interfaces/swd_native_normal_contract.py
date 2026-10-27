"""Host-only OpenOCD-like NORMAL SWD transaction contract.

NOT a compiled OpenOCD adapter or an ARMv7 MMIO implementation. Uses the
same injected SwdSiteController as the PS control layer. No physical I/O,
legacy GPIO/WordPort fallback, implicit WAIT retry, or fake AP RDBUFF.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock

from .swd_site import (
    SwdSiteController, SiteCompletion, SiteStatus, SiteAccessError,
    encode_transfer, encode_swj,
)


class SwdNormalAdapterError(SiteAccessError):
    def __init__(self, message: str, *, completion: SiteCompletion | None = None):
        super().__init__(message)
        self.completion = completion


class OperationKind(Enum):
    READ = "read"
    WRITE = "write"
    SWJ = "swj"


@dataclass(frozen=True)
class Pending:
    kind: OperationKind
    ap: bool = False
    addr: int = 0
    value: int = 0
    count: int = 0
    bits: int = 0


@dataclass(frozen=True)
class NormalResult:
    tag: int
    kind: OperationKind
    ack: int
    data: int | None


class SwdNativeNormalContract:
    """Inert read_reg/write_reg/switch_seq/run contract for ONE leased Site.

    The caller must verify Image/Manifest, exclusive lease, v5 identity and
    NORMAL mode independently. The current host-only implementation submits
    at most one transaction at a time, even though FPGA FIFO depth is 16.
    """

    def __init__(self, site: SwdSiteController, *, max_queue: int = 16):
        if not isinstance(site, SwdSiteController):
            raise TypeError("Explicit Site controller required")
        if type(max_queue) is not int or not 1 <= max_queue <= 16:
            raise ValueError("Queue depth must be 1..16")
        self._site = site
        self._max_queue = max_queue
        self._pending: list[Pending] = []
        self._tag = 1
        self._blocked = False
        self._lock = RLock()

    @property
    def site_id(self) -> int:
        return self._site.site_id

    def _queue(self, op: Pending) -> None:
        with self._lock:
            if self._blocked or self._site.poisoned:
                raise SwdNormalAdapterError("Adapter blocked: external recovery required")
            if len(self._pending) >= self._max_queue:
                raise SwdNormalAdapterError("Bounded NORMAL queue full")
            if self._tag + len(self._pending) > 0xFFFF:
                raise SwdNormalAdapterError("Tag space exhausted: no reuse")
            self._pending.append(op)

    def read_reg(self, *, ap: bool, address: int) -> None:
        encode_transfer(ap=ap, read=True, address=address)
        self._queue(Pending(OperationKind.READ, ap=ap, addr=address))

    def write_reg(self, *, ap: bool, address: int, value: int) -> None:
        encode_transfer(ap=ap, read=False, address=address)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("Unsigned full-word SWD data required")
        self._queue(Pending(OperationKind.WRITE, ap=ap, addr=address, value=value))

    def switch_seq(self, *, bit_count: int, bits: int = 0) -> None:
        encode_swj(bit_count)
        if type(bits) is not int or bits < 0 or bits >> bit_count:
            raise ValueError("SWJ bits out of range")
        self._queue(Pending(OperationKind.SWJ, count=bit_count, bits=bits))

    def run(self) -> tuple[NormalResult, ...]:
        with self._lock:
            if self._blocked or self._site.poisoned:
                raise SwdNormalAdapterError("Adapter blocked: external recovery required")
            pending = self._pending
            self._pending = []  # consumed before I/O; never replay on error
            results = []
            for op in pending:
                if self._tag > 0xFFFF:
                    self._blocked = True
                    raise SwdNormalAdapterError("Tag space exhausted")
                tag = self._tag
                self._tag += 1
                try:
                    if op.kind is OperationKind.SWJ:
                        self._site.enqueue_swj(tag=tag, bit_count=op.count, bits=op.bits)
                    else:
                        command = encode_transfer(
                            ap=op.ap, read=op.kind is OperationKind.READ,
                            address=op.addr)
                        self._site.enqueue(tag=tag, command=command, data=op.value)
                    c = self._site.next_completion()
                except (SiteAccessError, ValueError) as exc:
                    self._blocked = True
                    raise SwdNormalAdapterError(
                        "Uncertain SWD transfer; never auto-replay") from exc
                if c.tag != tag or c.status is not SiteStatus.OK:
                    self._blocked = True
                    raise SwdNormalAdapterError(
                        f"SWD result tag={c.tag} status={c.status.name}; no retry",
                        completion=c)
                if op.kind is not OperationKind.SWJ and c.ack != 0b001:
                    self._blocked = True
                    raise SwdNormalAdapterError("Incorrect raw SWD ACK", completion=c)
                needs_data = op.kind is OperationKind.READ
                if c.data_valid != needs_data:
                    self._blocked = True
                    raise SwdNormalAdapterError(
                        "Unexpected response data-valid bit", completion=c)
                results.append(NormalResult(
                    tag=tag, kind=op.kind, ack=c.ack,
                    data=c.data if needs_data else None))
            return tuple(results)
