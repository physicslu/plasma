from __future__ import annotations

from pathlib import Path

import pytest

from plasma_web import gateway_phase2, gateway_phase3
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


def test_phase2_startup_uses_explicit_runner_without_handler_global_replacement() -> None:
    phase2 = (ROOT / "software/python/plasma_web/gateway_phase2.py").read_text(encoding="utf-8")

    assert "serve_handler(" in phase2
    assert "canonical_gateway.PlasmaWebHandler =" not in phase2
    assert "canonical_gateway.main()" not in phase2
    assert "_strip_phase2_options" not in phase2


def test_phase3_startup_does_not_chain_or_replace_handler_globals() -> None:
    phase3 = (ROOT / "software/python/plasma_web/gateway_phase3.py").read_text(encoding="utf-8")
    secure = (ROOT / "software/python/plasma_web/secure_gateway_app.py").read_text(encoding="utf-8")

    assert "\n        phase2.main()" not in phase3
    assert "\n    phase2.main()" not in phase3
    assert "phase2.PlasmaWebHandler =" not in phase3
    assert "canonical_gateway.PlasmaWebHandler =" not in phase3
    assert "gateway.PlasmaWebHandler =" not in secure
    assert "gateway.main(handler_class=DeployedSecurePlasmaWebHandler)" in secure


def test_phase2_parser_retains_canonical_runtime_options() -> None:
    args = gateway_phase2._parser().parse_args(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "18080",
            "--plasma-host",
            "127.0.0.1",
            "--plasma-port",
            "9900",
            "--network-activation-socket",
            "/tmp/plasma-network.sock",
            "--ppu-config",
            "/tmp/ppu.yaml",
            "--engineering-mock",
        ]
    )
    assert args.port == 18080
    assert args.plasma_port == 9900
    assert args.engineering_mock is True


def test_phase3_provider_modes_are_parser_mutually_exclusive() -> None:
    parser = gateway_phase3._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--engineering-mock", "--engineering-configured-mock"])


def test_explicit_gateway_runner_owns_handler_selection() -> None:
    source = (ROOT / "software/python/plasma_web/gateway_runner.py").read_text(encoding="utf-8")
    assert "ThreadingHTTPServer((host, port), handler_class)" in source
    assert "canonical_gateway.PlasmaWebHandler =" not in source
