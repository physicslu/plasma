"""Bounded, best-effort pre-start correction through the local chrony service.

The only mutating command is chronyc's immediate ``makestep``.  In particular
this module never arms a future step, starts a burst, accepts a supplied time,
or runs a shell.  The PPU service account must already be authorised by the
locally configured chronyd socket; lack of that authority is a warning.
"""
from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable


STATUSES = frozenset({"SYNCED", "CORRECTED", "SKIPPED_BUSY", "UNAVAILABLE",
                      "UNTRUSTED_SOURCE", "TIMEOUT", "FAILED", "UNSUPPORTED"})
_SYSTEM_TIME = re.compile(r"^([0-9]+(?:\.[0-9]+)?) seconds (fast|slow) of NTP time$")


class _CommandError(RuntimeError):
    def __init__(self, status: str, code: str) -> None:
        self.status = status
        self.code = code


def _tracking(raw: str) -> tuple[float | None, float | None, str | None]:
    fields = dict(line.split(":", 1) for line in raw.splitlines() if ":" in line)
    fields = {key.strip(): value.strip() for key, value in fields.items()}
    if fields.get("Leap status") != "Normal":
        return None, None, "LEAP_NOT_NORMAL"
    try:
        stratum = int(fields["Stratum"])
        reference = fields["Reference ID"].split(" ", 1)[0]
        dispersion = float(fields["Root dispersion"].split()[0])
        match = _SYSTEM_TIME.fullmatch(fields["System time"])
        if not 1 <= stratum <= 15 or reference in {"00000000", "7F7F0101"}:
            return None, None, "NO_UPSTREAM_REFERENCE"
        if match is None or not 0 <= dispersion <= 1:
            return None, None, "MEASUREMENT_UNTRUSTED"
        offset = float(match.group(1)) * (1 if match.group(2) == "fast" else -1)
        return offset, dispersion, None
    except (KeyError, ValueError, IndexError):
        return None, None, "TRACKING_INVALID"


class ChronyTimeSync:
    """One bounded operation; runner injection keeps Host tests clock-free."""

    def __init__(self, runner: Callable[..., Any] = subprocess.run,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.runner = runner
        self.monotonic = monotonic

    def execute(self, *, ppu_id: str, threshold_ms: int = 100,
                budget_ms: int = 1000) -> dict[str, Any]:
        if type(threshold_ms) is not int or not 1 <= threshold_ms <= 1000:
            raise ValueError("threshold_ms must be 1..1000")
        if type(budget_ms) is not int or not 100 <= budget_ms <= 5000:
            raise ValueError("budget_ms must be 100..5000")
        started = self.monotonic()
        deadline = started + budget_ms / 1000
        result: dict[str, Any] = {
            "ppu_id": ppu_id, "status": "UNAVAILABLE", "source": "chronyd",
            "service": "chrony", "before_offset_ms": None,
            "after_offset_ms": None, "uncertainty_ms": None,
            "adjustment_performed": False, "warning_code": None,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        def invoke(command: str) -> str:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(["chronyc", "-n", command], budget_ms / 1000)
            completed = self.runner(["chronyc", "-n", command], check=False,
                                    capture_output=True, text=True, timeout=remaining,
                                    stdin=subprocess.DEVNULL)
            if completed.returncode != 0:
                detail = completed.stderr.lower()
                if "permission" in detail or "not authorised" in detail or "not authorized" in detail:
                    raise _CommandError("FAILED", "CHRONYC_PERMISSION_DENIED")
                if command == "tracking" and ("cannot talk to daemon" in detail
                                              or "506 cannot talk" in detail):
                    raise _CommandError("UNAVAILABLE", "CHRONYD_UNAVAILABLE")
                raise _CommandError("FAILED", "CHRONYC_" + command.upper() + "_REFUSED")
            return completed.stdout

        try:
            before, uncertainty, error = _tracking(invoke("tracking"))
            if error is not None:
                result.update(status="UNTRUSTED_SOURCE", warning_code=error)
            else:
                result["before_offset_ms"] = round(before * 1000, 3)
                result["uncertainty_ms"] = round(uncertainty * 1000, 3)
                if uncertainty * 1000 > threshold_ms:
                    result.update(status="UNTRUSTED_SOURCE",
                                  warning_code="SOURCE_UNCERTAINTY_HIGH")
                elif abs(before) * 1000 <= threshold_ms:
                    result["status"] = "SYNCED"
                    result["after_offset_ms"] = result["before_offset_ms"]
                else:
                    # No ``makestep threshold updates`` form: that would arm a
                    # later clock jump during a Batch after this request ended.
                    invoke("makestep")
                    result["adjustment_performed"] = True
                    after, after_uncertainty, error = _tracking(invoke("tracking"))
                    if error is not None:
                        result.update(status="FAILED", warning_code="POST_" + error)
                    else:
                        result["after_offset_ms"] = round(after * 1000, 3)
                        result["uncertainty_ms"] = round(after_uncertainty * 1000, 3)
                        if after_uncertainty * 1000 > threshold_ms:
                            result.update(status="FAILED", warning_code="POST_UNCERTAINTY_HIGH")
                        elif abs(after) * 1000 <= threshold_ms:
                            result["status"] = "CORRECTED"
                        else:
                            result.update(status="FAILED", warning_code="OFFSET_REMAINS_HIGH")
        except FileNotFoundError:
            result.update(status="UNSUPPORTED", warning_code="CHRONYC_NOT_INSTALLED")
        except subprocess.TimeoutExpired:
            result.update(status="TIMEOUT", warning_code="CHRONYC_TIMEOUT")
        except PermissionError:
            result.update(status="FAILED", warning_code="CHRONYC_PERMISSION_DENIED")
        except _CommandError as exc:
            result.update(status=exc.status, warning_code=exc.code)
        except (OSError, RuntimeError) as exc:
            result.update(status="UNAVAILABLE" if isinstance(exc, OSError) else "FAILED",
                          warning_code=type(exc).__name__.upper())
        result["elapsed_ms"] = round((self.monotonic() - started) * 1000, 3)
        return result
