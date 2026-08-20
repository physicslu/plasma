from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from .errors import ErrorCode, PlasmaError

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ProgrammingAssetType(StrEnum):
    IMAGE = "image"
    KEY = "key"
    OPTION = "option"
    SERIAL_NUMBER = "serial_number"
    CALIBRATION = "calibration"


class ProgrammingAssetFormat(StrEnum):
    BINARY = "binary"
    INTEL_HEX = "intel_hex"
    SREC = "srec"
    ELF = "elf"
    CSV = "csv"
    TEXT = "text"
    JSON = "json"
    PEM = "pem"


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    """Canonical bytes that will be programmed to or verified against target IC memory."""

    name: str
    data: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass(frozen=True, slots=True)
class ProgrammingAsset:
    """Materialized source data consumed by a programming workflow.

    An Asset describes source data, not PPU execution instructions. Recipe or
    manifest semantics belong to separate control-plane objects. The current
    implementation materializes uploaded assets as bytes; future providers may
    obtain equivalent assets from MES, databases, APIs or secure stores.
    """

    name: str
    asset_type: ProgrammingAssetType
    asset_format: ProgrammingAssetFormat
    data: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.data)

    @classmethod
    def from_upload(
        cls,
        *,
        name: str,
        asset_type: str,
        asset_format: str,
        data: bytes,
        sha256: str,
    ) -> "ProgrammingAsset":
        if not isinstance(name, str) or not name.strip():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "asset_name is required")
        if not isinstance(data, bytes) or not data:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Programming Asset upload is empty")
        if not isinstance(sha256, str) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "invalid asset_sha256")
        try:
            parsed_type = ProgrammingAssetType(asset_type)
        except ValueError as exc:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"unsupported asset_type: {asset_type!r}",
            ) from exc
        try:
            parsed_format = ProgrammingAssetFormat(asset_format)
        except ValueError as exc:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"unsupported asset_format: {asset_format!r}",
            ) from exc
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != sha256:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "asset_sha256 does not match uploaded bytes",
                context={"expected": sha256, "actual": actual_sha256},
            )
        return cls(
            name=name.strip(),
            asset_type=parsed_type,
            asset_format=parsed_format,
            data=data,
            sha256=sha256,
        )

    def normalize_image(self) -> NormalizedImage:
        """Convert an Image Asset into the canonical execution image.

        Only raw binary Image Assets are implemented today. HEX/SREC/ELF/CSV/
        text inputs and non-Image Asset types fail closed until a real parser or
        consumer is implemented and validated.
        """
        if self.asset_type is not ProgrammingAssetType.IMAGE:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"asset_type {self.asset_type.value!r} cannot be normalized as an Image",
            )
        if self.asset_format is not ProgrammingAssetFormat.BINARY:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"asset_format {self.asset_format.value!r} has no Image parser yet",
            )
        return NormalizedImage(
            name=self.name,
            data=self.data,
            sha256=hashlib.sha256(self.data).hexdigest(),
        )
