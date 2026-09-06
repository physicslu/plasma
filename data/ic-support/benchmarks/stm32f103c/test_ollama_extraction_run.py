from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ollama_extraction_run as runner
import score_single_run as single_scorer
from test_ab_benchmark import evidence_for, synthetic_observed, synthetic_run

HERE = Path(__file__).resolve().parent


class _NativeChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    last_payload: dict | None = None

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).last_payload = payload
        body = json.dumps(
            {
                "model": "synthetic-model",
                "message": {"role": "assistant", "content": "{\"ok\":true}"},
                "done": True,
                "done_reason": "stop",
                "total_duration": 1000,
                "load_duration": 100,
                "prompt_eval_count": 123,
                "prompt_eval_cached_count": 23,
                "prompt_eval_duration": 500,
                "eval_count": 10,
                "eval_duration": 400,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class OllamaExtractionRunTest(unittest.TestCase):
    def test_generation_module_does_not_name_answer_key(self):
        source = (HERE / "ollama_extraction_run.py").read_text(encoding="utf-8")
        self.assertNotIn("extraction-ground-truth", source)
        self.assertNotIn("ground-truth.json", source)

    def test_native_chat_sends_explicit_bounded_context_controls(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _NativeChatHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = runner.ollama_native_chat(
                ollama_url=f"http://127.0.0.1:{server.server_port}",
                model="synthetic-model",
                prompt="synthetic prompt",
                num_ctx=65536,
                max_tokens=4096,
                temperature=0.0,
                seed=7,
                timeout_seconds=5.0,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1.0)

        payload = _NativeChatHandler.last_payload
        self.assertIsInstance(payload, dict)
        assert payload is not None
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertFalse(payload["truncate"])
        self.assertFalse(payload["shift"])
        self.assertEqual(payload["options"]["num_ctx"], 65536)
        self.assertEqual(payload["options"]["num_predict"], 4096)
        self.assertEqual(payload["options"]["seed"], 7)
        self.assertEqual(result["prompt_eval_count"], 123)
        self.assertEqual(result["prompt_eval_cached_count"], 23)
        self.assertEqual(result["eval_count"], 10)
        self.assertEqual(result["done_reason"], "stop")

    def test_single_run_scorer_reuses_isolated_score_contract(self):
        observed = synthetic_observed()
        run = synthetic_run("reduced_context", observed, evidence_for(observed))
        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "reduced_context.run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = single_scorer.score_single(run_path)
        self.assertEqual(report["arm"], "reduced_context")
        self.assertEqual(report["score"]["status"], "scored")
        self.assertFalse(report["score_authority"]["generation_path_reads_ground_truth"])


if __name__ == "__main__":
    unittest.main()
