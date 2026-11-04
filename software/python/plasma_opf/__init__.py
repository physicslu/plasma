"""PLASMA Open Provider Framework (OPF) contract-only foundation.

This package does not load Providers, allocate Sites, or execute hardware work.
"""
from .contract import (
    OPF_PROGRAMMING_SCHEMA,
    OpfContractError,
    ProgrammingSelection,
    TimeoutPolicy,
    parse_programming_selection,
)

__all__ = [
    "OPF_PROGRAMMING_SCHEMA",
    "OpfContractError",
    "ProgrammingSelection",
    "TimeoutPolicy",
    "parse_programming_selection",
]
