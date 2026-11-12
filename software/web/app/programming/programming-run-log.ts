import type { ProgrammingRun } from "../engineering/bundle-programming-api";
import { runVerdict } from "./managed-programming";

const hex = (value: number) => `0x${value.toString(16).toUpperCase().padStart(8, "0")}`;

/** SAFE_OFF as the Manager receipt reports it; never inferred from a PASS. */
export function safeOffLogLabel(safeOff: boolean | null | undefined, finished: boolean): string {
  return safeOff === true ? "VERIFIED" : finished ? "NOT VERIFIED" : "—";
}

/**
 * The traceable record of one Manager programming run, as Log lines.
 *
 * EMode (Engineering Job Log) and PMode (Factory Log) both write these, so the
 * Log is the single on-screen operation record: Run ID, Job ID, verdict,
 * reason, SAFE_OFF and the identities the PPU confirmed. It is a summary of
 * the Manager run record, never the full JSON Receipt; the Manager keeps that.
 */
export function programmingRunLogLines(
  run: ProgrammingRun,
  options: { executionInterface?: string | null } = {},
): string[] {
  const { verdict, reason } = runVerdict(run);
  const receipt = run.receipt;
  const finished = run.outcome != null;
  const lines = [
    `[RUN] ${verdict.replace("_", " ")}${reason ? ` · ${reason}` : ""} · Run ${run.run_id} · Job ${receipt?.job_id ?? run.job?.job_id ?? "—"}`
      + ` · PPU ${run.ppu_alias} · Site ${run.site_id} · SAFE_OFF ${safeOffLogLabel(receipt?.safe_off, finished)}`
      + ` · attempts ${run.job_submission_count} · auto retry ${run.auto_retry}`,
  ];
  if (run.steps.length) {
    lines.push(`[STEPS] ${run.steps.map(step => `${step.step}: ${step.result}`).join(" · ")}`);
  }
  if (receipt) {
    const operations = receipt.operations
      ? `${receipt.operations.join(" → ")} (one Job · PPU ran: ${receipt.observed_operations?.join(" → ") ?? "not reported"})`
      : receipt.operation ?? "—";
    lines.push(
      `[RECEIPT] Job ${receipt.job_id ?? "—"} · Operations ${operations}`
      + ` · Range ${receipt.range ? `${hex(receipt.range.address)} + ${receipt.range.length} B` : "—"}`
      + ` · Resources ${receipt.resource_reuse ? "Reused" : "Activated"}`
      + ` · Verified ${receipt.bytes_verified ?? "—"} / ${receipt.expected_image_size ?? "—"} B`
      + ` · Readback SHA256 ${receipt.readback_sha256 ?? "—"}`,
    );
    lines.push(
      `[RECEIPT] Resource SHA256 ${receipt.observed_resource_set_sha256 ?? "—"}`
      + ` · Job Binding SHA256 ${receipt.observed_job_binding_sha256 ?? "—"}`,
    );
  }
  if (options.executionInterface !== undefined) {
    lines.push(options.executionInterface === "mock"
      ? "[EVIDENCE] MOCK RESULT · Site interface mock · not hardware evidence and never a hardware qualification"
      : `[EVIDENCE] Site interface: ${options.executionInterface ?? "not reported"}`);
  }
  return lines;
}
