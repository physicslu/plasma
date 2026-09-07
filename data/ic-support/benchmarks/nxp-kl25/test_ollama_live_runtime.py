#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from unittest import mock

import ollama_live_runtime as runtime
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


class KL25OllamaLiveRuntimeTest(unittest.TestCase):
    def test_loopback_policy_accepts_local_endpoints_only(self):
        self.assertEqual(runtime.normalize_loopback_ollama_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434")
        self.assertEqual(runtime.normalize_loopback_ollama_url("http://localhost:11434/"), "http://localhost:11434")
        self.assertEqual(runtime.normalize_loopback_ollama_url("http://[::1]:11434"), "http://[::1]:11434")
        for value in (
            "https://127.0.0.1:11434",
            "http://192.168.1.10:11434",
            "http://example.com:11434",
            "http://user:pass@127.0.0.1:11434",
            "http://127.0.0.1:11434/api/chat",
        ):
            with self.subTest(value=value):
                with self.assertRaises(runner.SemanticTransportProtocolError):
                    runtime.normalize_loopback_ollama_url(value)

    def test_runtime_identity_locks_version_and_exact_model_digest(self):
        responses = [
            FakeResponse(json.dumps({"version": "0.12.0"}).encode()),
            FakeResponse(
                json.dumps(
                    {
                        "models": [
                            {
                                "name": "qwen3.8:27b-mlx",
                                "model": "qwen3.8:27b-mlx",
                                "digest": "sha256:" + "a" * 64,
                                "size": 123456,
                                "modified_at": "2026-09-01T00:00:00Z",
                            }
                        ]
                    }
                ).encode()
            ),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as mocked:
            identity = runtime.query_ollama_runtime_identity(
                ollama_url="http://127.0.0.1:11434",
                model_id="qwen3.8:27b-mlx",
                timeout_seconds=10.0,
            )
        self.assertEqual(identity["ollama_version"], "0.12.0")
        self.assertEqual(identity["model_digest"], "sha256:" + "a" * 64)
        self.assertEqual(identity["model_id"], "qwen3.8:27b-mlx")
        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(mocked.call_args_list[0].args[0].full_url.endswith("/api/version"))
        self.assertTrue(mocked.call_args_list[1].args[0].full_url.endswith("/api/tags"))

    def test_missing_or_ambiguous_model_fails_closed(self):
        version = FakeResponse(json.dumps({"version": "0.12.0"}).encode())
        missing = FakeResponse(json.dumps({"models": []}).encode())
        with mock.patch("urllib.request.urlopen", side_effect=[version, missing]):
            with self.assertRaises(runner.SemanticTransportProtocolError):
                runtime.query_ollama_runtime_identity(
                    ollama_url="http://127.0.0.1:11434",
                    model_id="qwen3.8:27b-mlx",
                )

    def test_malformed_model_digest_fails_closed(self):
        version = FakeResponse(json.dumps({"version": "0.12.0"}).encode())
        tags = FakeResponse(
            json.dumps({"models": [{"name": "qwen3.8:27b-mlx", "digest": "not-a-digest"}]}).encode()
        )
        with mock.patch("urllib.request.urlopen", side_effect=[version, tags]):
            with self.assertRaises(runner.SemanticTransportProtocolError):
                runtime.query_ollama_runtime_identity(
                    ollama_url="http://127.0.0.1:11434",
                    model_id="qwen3.8:27b-mlx",
                )


if __name__ == "__main__":
    unittest.main()
