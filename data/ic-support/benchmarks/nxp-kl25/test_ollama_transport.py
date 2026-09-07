#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest import mock

import ollama_transport
import semantic_runner as runner


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class KL25OllamaTransportTest(unittest.TestCase):
    def invoke(self, **overrides):
        options = {
            "ollama_url": "http://127.0.0.1:11434",
            "num_ctx": 32768,
            "max_tokens": 2048,
            "temperature": 0.0,
            "seed": 7,
            "timeout_seconds": 30.0,
        }
        options.update(overrides.pop("options", {}))
        return ollama_transport.ollama_native_chat_transport(
            prompt=overrides.pop("prompt", "manufacturer evidence prompt"),
            model_id=overrides.pop("model_id", "qwen3.8:27b-mlx"),
            runtime_label=overrides.pop("runtime_label", "repository-ci"),
            options=options,
            **overrides,
        )

    def test_native_chat_request_has_bounded_non_streaming_controls(self):
        captured = {}
        outer = {
            "model": "qwen3.8:27b-mlx",
            "message": {"role": "assistant", "content": "{\"schema_version\":\"0.1.0\"}"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 20,
        }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(json.dumps(outer).encode("utf-8"))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = self.invoke()

        self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(captured["timeout"], 30.0)
        payload = captured["payload"]
        self.assertEqual(payload["model"], "qwen3.8:27b-mlx")
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertFalse(payload["truncate"])
        self.assertFalse(payload["shift"])
        self.assertEqual(payload["messages"], [{"role": "user", "content": "manufacturer evidence prompt"}])
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertEqual(payload["options"]["num_predict"], 2048)
        self.assertEqual(payload["options"]["temperature"], 0.0)
        self.assertEqual(payload["options"]["seed"], 7)
        self.assertEqual(result["raw_text"], "{\"schema_version\":\"0.1.0\"}")
        self.assertEqual(result["response_model"], "qwen3.8:27b-mlx")
        self.assertEqual(result["usage"]["input_tokens"], 100)
        self.assertEqual(result["usage"]["generation_tokens"], 20)

    def test_timeout_is_normalized(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("mock timeout")):
            with self.assertRaises(runner.SemanticTransportTimeout):
                self.invoke()

    def test_connection_failure_is_normalized(self):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError(ConnectionRefusedError("mock refused")),
        ):
            with self.assertRaises(runner.SemanticTransportUnavailable):
                self.invoke()

    def test_http_error_is_normalized(self):
        http_error = urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/chat",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b"model unavailable"),
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(runner.SemanticTransportUnavailable):
                self.invoke()

    def test_malformed_outer_json_is_protocol_error(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"not-json")):
            with self.assertRaises(runner.SemanticTransportProtocolError):
                self.invoke()

    def test_missing_message_content_is_protocol_error(self):
        body = json.dumps({"model": "qwen3.8:27b-mlx", "message": {}}).encode("utf-8")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(body)):
            with self.assertRaises(runner.SemanticTransportProtocolError):
                self.invoke()

    def test_invalid_request_bounds_fail_before_http(self):
        with mock.patch("urllib.request.urlopen") as mocked:
            with self.assertRaises(runner.SemanticTransportProtocolError):
                self.invoke(options={"num_ctx": 0})
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
