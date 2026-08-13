"""Network client and command-line interface for Plasma."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import PlasmaClient

__all__ = ["PlasmaClient"]


def __getattr__(name: str) -> Any:
    if name == "PlasmaClient":
        from .client import PlasmaClient

        return PlasmaClient
    raise AttributeError(name)
