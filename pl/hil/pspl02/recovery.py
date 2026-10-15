"""Offline recovery acceptance only; never loads firmware or changes services."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from pl.hil.pspl02 import contract as c


def verify(before: dict, after: dict, observed: dict):
    for snapshot in (before, after):
        c._require(snapshot.get("architecture") == "armv7l"
                   and snapshot.get("device_model_confirmed") is True
                   and snapshot.get("pynq_version") == "3.1.1", "Wrong restored platform")
        c._require(snapshot.get("fpga_manager_state") == "operating"
                   and snapshot.get("fclk0_hz") == 100_000_000
                   and snapshot.get("fclk0_enabled") is True, "Manager/clock mismatch")
        c._require(snapshot.get("services") == dict.fromkeys(c.SERVICES, "active"),
                   "Services not restored")
    for field in ("metadata_sha256", "driver_bindings", "uio"):
        old, new = before.get(field), after.get(field)
        c._require(bool(old) and bool(new), "Missing recovery snapshot: " + field)
        if field == "uio":
            # Indexes may be renumbered. Compare resource identity instead.
            def rows(value):
                return sorted((x["name"], x["address"], x["size"]) for x in value)
            c._require(rows(old) == rows(new), "UIO resources differ")
        else:
            c._require(old == new, "Original state differs: " + field)
    c._require(observed.get("recovery_sha256") == {k: c.HASHES[k] for k in ("base.bin", "base.hwh")},
               "Wrong recovery image pair")
    for field in ("base_loaded_once_and_operating", "metadata_backup_matches",
                  "drivers_restored", "ssh_verified", "uart_still_usable",
                  "jupyter_http_verified", "gateway_live_verified", "gateway_ready_verified",
                  "no_new_kernel_axi_or_fpga_errors", "no_shared_service_changes",
                  "no_ps7_init_or_ddr_reinitialization"):
        c._require(observed.get(field) is True, "Missing recovery observation: " + field)
    return {"qualification": "PSPL-02/SWD-00", "restoration": "PASS",
            "method": "offline_comparison_of_separately_observed_evidence",
            "physical_swd": "NOT_RUN", "ic_programming": "NOT_RUN"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "observed", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        c._require(not args.output.exists(), "Refuse overwrite")
        result = verify(c.json_object(args.before), c.json_object(args.after), c.json_object(args.observed))
        c.write_record(args.output, result)
    except (OSError, ValueError, KeyError, TypeError, c.SafetyError) as exc:
        print("PSPL02_RECOVERY_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("PSPL02_RECOVERY_EVIDENCE_PASS_HIL_RESULTS_RECORDED_SEPARATELY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
