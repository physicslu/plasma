from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ErrorCode, PlasmaError
from .mock_image_store import SharedImageStore


@dataclass(frozen=True, slots=True)
class BackingRegion:
    address: int
    length: int
    image_sha256: str
    image_offset: int = 0

    @property
    def end(self) -> int:
        return self.address + self.length


@dataclass(slots=True)
class SparseOverlay:
    """Small copy-on-write regions layered above immutable shared images."""

    _regions: dict[int, bytes] = field(default_factory=dict)

    def clear(self) -> None:
        self._regions.clear()

    def write(self, address: int, data: bytes) -> None:
        if isinstance(address, bool) or not isinstance(address, int) or address < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "overlay address must be a non-negative integer")
        if not isinstance(data, bytes):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "overlay data must be bytes")
        if not data:
            return
        self.remove_range(address, len(data))
        self._regions[address] = data

    def remove_range(self, address: int, length: int) -> None:
        if address < 0 or length < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "overlay removal range is invalid")
        if length == 0:
            return
        end = address + length
        replacement: dict[int, bytes] = {}
        for region_address, data in self._regions.items():
            region_end = region_address + len(data)
            if region_end <= address or region_address >= end:
                replacement[region_address] = data
                continue
            if region_address < address:
                replacement[region_address] = data[: address - region_address]
            if region_end > end:
                replacement[end] = data[end - region_address :]
        self._regions = replacement

    def apply(self, address: int, output: bytearray) -> None:
        end = address + len(output)
        for region_address, data in self._regions.items():
            region_end = region_address + len(data)
            overlap_start = max(address, region_address)
            overlap_end = min(end, region_end)
            if overlap_start >= overlap_end:
                continue
            output[overlap_start - address : overlap_end - address] = data[
                overlap_start - region_address : overlap_end - region_address
            ]


@dataclass(slots=True)
class MockFlashState:
    flash_size_bytes: int
    backing_regions: list[BackingRegion] = field(default_factory=list)
    overlay: SparseOverlay = field(default_factory=SparseOverlay)

    def __post_init__(self) -> None:
        if (
            isinstance(self.flash_size_bytes, bool)
            or not isinstance(self.flash_size_bytes, int)
            or self.flash_size_bytes <= 0
        ):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "mock flash size must be a positive integer")

    def erase(self, address: int = 0, length: int | None = None) -> None:
        length = self.flash_size_bytes - address if length is None else length
        self._validate_range(address, length)
        if address == 0 and length == self.flash_size_bytes:
            self.backing_regions.clear()
            self.overlay.clear()
            return

        # Partial erase is represented as 0xFF copy-on-write data. Keeping the
        # immutable backing regions lets bytes outside the erased range survive.
        self.overlay.write(address, bytes([0xFF]) * length)

    def program_shared(
        self,
        *,
        image_sha256: str,
        image_size_bytes: int,
        address: int = 0,
        image_offset: int = 0,
    ) -> None:
        self._validate_range(address, image_size_bytes)
        if isinstance(image_offset, bool) or not isinstance(image_offset, int) or image_offset < 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "image_offset must be a non-negative integer")
        new_end = address + image_size_bytes
        # Remove only backing regions completely superseded by this Program.
        # Partially overlapping older regions remain underneath; read order makes
        # the newly appended region authoritative for the overlap.
        self.backing_regions = [
            region
            for region in self.backing_regions
            if not (address <= region.address and region.end <= new_end)
        ]
        self.backing_regions.append(
            BackingRegion(
                address=address,
                length=image_size_bytes,
                image_sha256=image_sha256,
                image_offset=image_offset,
            )
        )
        self.overlay.remove_range(address, image_size_bytes)

    def read(self, store: SharedImageStore, address: int, length: int) -> bytes:
        self._validate_range(address, length)
        output = bytearray([0xFF]) * length
        request_end = address + length
        for region in self.backing_regions:
            overlap_start = max(address, region.address)
            overlap_end = min(request_end, region.end)
            if overlap_start >= overlap_end:
                continue
            ref = store.resolve(region.image_sha256)
            blob_start = region.image_offset + overlap_start - region.address
            blob_end = blob_start + overlap_end - overlap_start
            if blob_end > ref.size_bytes:
                raise PlasmaError(
                    ErrorCode.INTERNAL_ERROR,
                    "mock backing region exceeds shared image bounds",
                    context={"sha256": region.image_sha256},
                )
            with store.open_mmap(region.image_sha256) as mapped:
                output[overlap_start - address : overlap_end - address] = mapped[blob_start:blob_end]
        self.overlay.apply(address, output)
        return bytes(output)

    def verify(self, store: SharedImageStore, expected: bytes, address: int = 0) -> int | None:
        actual = self.read(store, address, len(expected))
        for index, (observed, wanted) in enumerate(zip(actual, expected, strict=True)):
            if observed != wanted:
                return address + index
        return None

    def verify_shared(
        self,
        store: SharedImageStore,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
        address: int = 0,
        chunk_size: int = 64 * 1024,
    ) -> int | None:
        """Verify one shared image using bounded working memory.

        The expected Blob stays mmap-backed. Actual target state is read in
        chunks, so a 4 MiB Verify does not materialize another 4 MiB expected
        image for every concurrently executing Site.
        """
        self._validate_range(address, expected_size_bytes)
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "verify chunk_size must be positive")
        store.resolve(expected_sha256, expected_size=expected_size_bytes)
        with store.open_mmap(expected_sha256, expected_size=expected_size_bytes) as expected:
            for offset in range(0, expected_size_bytes, chunk_size):
                length = min(chunk_size, expected_size_bytes - offset)
                actual = self.read(store, address + offset, length)
                wanted = expected[offset : offset + length]
                if actual == wanted:
                    continue
                for index, (observed, expected_byte) in enumerate(zip(actual, wanted, strict=True)):
                    if observed != expected_byte:
                        return address + offset + index
        return None

    def _validate_range(self, address: int, length: int) -> None:
        if (
            isinstance(address, bool)
            or isinstance(length, bool)
            or not isinstance(address, int)
            or not isinstance(length, int)
            or address < 0
            or length < 0
            or address + length > self.flash_size_bytes
        ):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "flash address range is outside the mock target",
                context={"address": address, "length": length, "flash_size": self.flash_size_bytes},
            )
