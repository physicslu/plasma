from __future__ import annotations

import threading
import unittest

from plasma_manager.poller import FleetPoller


class BlockingFleetSource:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def fleet_snapshot(self):
        self.entered.set()
        if not self.release.wait(2.0):
            raise RuntimeError("test source was not released")
        return {
            "ok": True,
            "degraded": True,
            "observed_at": "after-release",
            "ppus": [],
        }


class FleetPollerStartupTests(unittest.TestCase):
    def test_nonblocking_initial_refresh_does_not_delay_service_startup(self) -> None:
        source = BlockingFleetSource()
        poller = FleetPoller(source, 60.0)
        start_returned = threading.Event()
        start_error: list[BaseException] = []

        def start_poller() -> None:
            try:
                poller.start(prime_cache=False)
            except BaseException as exc:  # pragma: no cover - assertion reports it below
                start_error.append(exc)
            finally:
                start_returned.set()

        caller = threading.Thread(target=start_poller, daemon=True)
        caller.start()
        try:
            self.assertTrue(source.entered.wait(1.0), "background initial refresh did not start")
            self.assertTrue(
                start_returned.wait(1.0),
                "non-blocking poller start waited for PPU/fleet refresh",
            )
            self.assertEqual(start_error, [])
            with self.assertRaisesRegex(RuntimeError, "snapshot cache is not initialized"):
                poller.snapshot()

            source.release.set()
            caller.join(timeout=1.0)

            deadline = threading.Event()
            for _ in range(100):
                try:
                    snapshot = poller.snapshot()
                except RuntimeError:
                    deadline.wait(0.01)
                    continue
                self.assertEqual(snapshot["observed_at"], "after-release")
                break
            else:
                self.fail("background initial refresh did not publish a snapshot")
        finally:
            source.release.set()
            caller.join(timeout=1.0)
            poller.stop(timeout_s=1.0)


if __name__ == "__main__":
    unittest.main()
