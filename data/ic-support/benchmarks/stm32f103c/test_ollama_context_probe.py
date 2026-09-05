from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ollama_context_probe as probe


class _ProbeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict] = []

    def log_message(self, format, *args):  # noqa: A003
        return

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        if self.path != "/api/ps":
            self._write_json(404, {"error": "not found"})
            return
        self._write_json(
            200,
            {
                "models": [
                    {
                        "name": "synthetic-model",
                        "model": "synthetic-model",
                        "digest": "a" * 64,
                        "size": 123,
                        "size_vram": 122,
                        "context_length": 32768,
                        "details": {
                            "family": "synthetic",
                            "parameter_size": "1B",
                            "quantization_level": "Q4",
                        },
                    }
                ]
            },
        )

    def do_POST(self):  # noqa: N802
        if self.path != "/api/chat":
            self._write_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append(payload)
        content = payload["messages"][0]["content"]
        if content == "FULL":
            self._write_json(
                400,
                {
                    "error": (
                        "input length (120000 tokens) exceeds the model's maximum "
                        "context length (32768 tokens)"
                    )
                },
            )
            return
        self._write_json(
            200,
            {
                "model": "synthetic-model",
                "done": True,
                "prompt_eval_count": 24000,
                "prompt_eval_duration": 100,
                "load_duration": 10,
                "total_duration": 200,
            },
        )


class OllamaContextProbeTest(unittest.TestCase):
    def setUp(self):
        _ProbeHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1.0)

    def test_over_context_reports_exact_runtime_token_demand(self):
        result = probe.probe_prompt(
            ollama_url=self.base_url,
            model="synthetic-model",
            prompt="FULL",
            num_ctx=32768,
            timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "over_context")
        self.assertEqual(result["prompt_tokens"], 120000)
        self.assertEqual(result["runtime_context_tokens"], 32768)
        self.assertEqual(result["headroom_tokens"], 32768 - 120000)

    def test_fitting_prompt_uses_runtime_prompt_eval_count(self):
        result = probe.probe_prompt(
            ollama_url=self.base_url,
            model="synthetic-model",
            prompt="REDUCED",
            num_ctx=32768,
            timeout_seconds=2.0,
        )
        self.assertEqual(result["status"], "fits_context")
        self.assertEqual(result["prompt_tokens"], 24000)
        self.assertEqual(result["headroom_tokens"], 8768)
        self.assertEqual(result["prompt_eval_duration_ns"], 100)

    def test_probe_disables_truncation_shift_and_thinking(self):
        probe.probe_prompt(
            ollama_url=self.base_url,
            model="synthetic-model",
            prompt="REDUCED",
            num_ctx=32768,
            timeout_seconds=2.0,
        )
        payload = _ProbeHandler.requests[-1]
        self.assertIs(payload["truncate"], False)
        self.assertIs(payload["shift"], False)
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertEqual(payload["options"]["num_predict"], 1)
        self.assertEqual(payload["options"]["temperature"], 0)

    def test_running_model_snapshot_records_active_context(self):
        snapshot = probe.running_model_snapshot(
            ollama_url=self.base_url,
            model="synthetic-model",
            timeout_seconds=2.0,
        )
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["context_length"], 32768)
        self.assertEqual(snapshot["quantization_level"], "Q4")


if __name__ == "__main__":
    unittest.main()
