"""Local Manager authority boundaries; never infer origin from transport types."""
from contextlib import contextmanager


class SharedControlError(RuntimeError):
    """A local Manager policy/store/configuration could not be judged."""


@contextmanager
def shared_boundary(stage, *, local_refusals=()):
    """Mark the actual local call site, preserving expected per-alias refusals.

    Reasons contain stage/type only: credential/configuration text is private.
    No network operation belongs inside this boundary.
    """
    try:
        yield
    except SharedControlError:
        raise
    except local_refusals:
        raise
    except Exception as exc:
        raise SharedControlError(f"{stage}_{type(exc).__name__}") from exc


def shared_control_reason(check):
    """Validate a trusted local-only check's complete verdict, not its truthiness."""
    if check is None:
        return None
    try:
        verdict = check()
        if verdict is None:
            return None
        if (not isinstance(verdict, tuple) or len(verdict) != 2
                or verdict[0] != "SHARED_CONTROL_FAILURE"
                or not isinstance(verdict[1], str) or not verdict[1]):
            raise ValueError("invalid shared authority verdict")
        return verdict[1]
    except Exception as exc:
        return f"GATE_NOT_EXECUTABLE_{type(exc).__name__}"
