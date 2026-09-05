from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ab_benchmark as harness


class ABBenchmarkTimeoutTest(unittest.TestCase):
    def test_raw_timeout_is_normalized_to_benchmark_error(self):
        with mock.patch.object(harness.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(harness.ABBenchmarkError, "timed out after 0.1 seconds"):
                harness.openai_compatible_chat(
                    base_url="http://127.0.0.1:11434/v1",
                    model="synthetic-model",
                    prompt="synthetic",
                    api_key=None,
                    temperature=0.0,
                    max_tokens=1,
                    seed=7,
                    timeout_seconds=0.1,
                )

    def test_run_pair_continues_after_error_record(self):
        calls: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            results = Path(tmp) / "results"

            def fake_load_arm_context(path: Path, arm_name: str):
                self.assertEqual(path, workspace)
                return "context", {}, {}

            def fake_execute_arm(**kwargs):
                arm_name = kwargs["arm_name"]
                calls.append(arm_name)
                return {"status": "error" if arm_name == "full_context" else "success"}

            with (
                mock.patch.object(harness, "load_arm_context", side_effect=fake_load_arm_context),
                mock.patch.object(harness, "execute_arm", side_effect=fake_execute_arm),
            ):
                harness.run_pair(
                    workspace=workspace,
                    results_dir=results,
                    base_url="http://unused/v1",
                    model="synthetic-model",
                    runtime_label="synthetic-runtime",
                    api_key=None,
                    trials=1,
                    temperature=0.0,
                    max_tokens=1,
                    seed=7,
                    timeout_seconds=0.1,
                    inter_arm_delay_seconds=0.0,
                )

        self.assertEqual(calls, ["full_context", "reduced_context"])


if __name__ == "__main__":
    unittest.main()
