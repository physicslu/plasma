from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from plasma_core.diagnostics import PL_LOOPBACK_ENDPOINT
from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_base as base
from . import gateway_phase2
from .pl_diagnostics import execute_pl_loopback


class PLQualificationWebHandler(gateway_phase2.Phase2PlasmaWebHandler):
    """Phase-2 Gateway plus one explicitly scoped real-PL diagnostic route."""

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/engineering/diagnostics/loopback":
            super().do_POST()
            return

        try:
            body = self._body()
            if body.get("endpoint") != PL_LOOPBACK_ENDPOINT:
                # Preserve the canonical PS path unchanged.
                self._cached_loopback_body = body
                super().do_POST()
                return
            try:
                payload = base._run(execute_pl_loopback(body, self.client_factory))
            except PlasmaError as exc:
                if exc.code in {ErrorCode.CONNECTION_FAILED, ErrorCode.CONNECTION_TIMEOUT}:
                    self._execution_unavailable()
                    return
                raise
            self._json(HTTPStatus.OK, base._with_rest_version(payload))
        except Exception as exc:
            self._error(exc)

    def _body(self):
        cached = getattr(self, "_cached_loopback_body", None)
        if cached is not None:
            del self._cached_loopback_body
            return cached
        return super()._body()


PlasmaWebHandler = PLQualificationWebHandler


def main() -> None:
    original = gateway_phase2.PlasmaWebHandler
    gateway_phase2.PlasmaWebHandler = PlasmaWebHandler
    try:
        gateway_phase2.main()
    finally:
        gateway_phase2.PlasmaWebHandler = original


if __name__ == "__main__":
    main()
