from __future__ import annotations

from pathlib import Path

import pytest

from plasma_web import gateway_phase3
from plasma_web.gateway_phase2 import PPUNetworkActivationSupportMixin, SiteConfigurationSupportMixin
from plasma_web.gateway_phase3 import Phase3PlasmaWebHandler, SiteRuntimeActivationSupportMixin
from plasma_web.secure_gateway_app import DeployedSecurePlasmaWebHandler


ROOT = Path(__file__).resolve().parents[3]


def test_phase3_handler_has_explicit_feature_composition() -> None:
    assert issubclass(Phase3PlasmaWebHandler, SiteRuntimeActivationSupportMixin)
    assert issubclass(Phase3PlasmaWebHandler, SiteConfigurationSupportMixin)
    assert issubclass(Phase3PlasmaWebHandler, PPUNetworkActivationSupportMixin)
    assert issubclass(DeployedSecurePlasmaWebHandler, SiteRuntimeActivationSupportMixin)
    assert issubclass(DeployedSecurePlasmaWebHandler, SiteConfigurationSupportMixin)
    assert issubclass(DeployedSecurePlasmaWebHandler, PPUNetworkActivationSupportMixin)


def test_phase3_startup_does_not_chain_or_replace_handler_globals() -> None:
    phase3 = (ROOT / "software/python/plasma_web/gateway_phase3.py").read_text(encoding="utf-8")
    secure = (ROOT / "software/python/plasma_web/secure_gateway_app.py").read_text(encoding="utf-8")

    assert "\n        phase2.main()" not in phase3
    assert "\n    phase2.main()" not in phase3
    assert "phase2.PlasmaWebHandler =" not in phase3
    assert "canonical_gateway.PlasmaWebHandler =" not in phase3
    assert "gateway.PlasmaWebHandler =" not in secure
    assert "gateway.main(handler_class=DeployedSecurePlasmaWebHandler)" in secure


def test_phase3_provider_modes_are_parser_mutually_exclusive() -> None:
    parser = gateway_phase3._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--engineering-mock", "--engineering-configured-mock"])


def test_explicit_gateway_runner_owns_handler_selection() -> None:
    source = (ROOT / "software/python/plasma_web/gateway_runner.py").read_text(encoding="utf-8")
    assert "ThreadingHTTPServer((host, port), handler_class)" in source
    assert "canonical_gateway.PlasmaWebHandler =" not in source
