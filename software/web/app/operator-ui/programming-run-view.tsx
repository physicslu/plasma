import type { ProgrammingRun } from "../engineering/bundle-programming-api";
import { runProgressPercent, runVerdict } from "../programming/managed-programming";
import "./programming-source-selector.css";

function verdictLabel(run: ProgrammingRun, verdict: string): string {
  if (verdict === "OUTCOME_UNKNOWN") return "OUTCOME UNKNOWN";
  if (verdict === "RUNNING") return run.state.toUpperCase();
  return verdict;
}

/**
 * Shared Job progress / Receipt / Error view (EMode, PMode, PPU → Platform).
 * Shows only what the Manager run record reports; identities are never
 * truncated so they can be used for technical diagnosis.
 */
export function ProgrammingRunView({
  run,
  onAcknowledge,
  acknowledging = false,
  ariaLabel = "Programming run",
  executionInterface,
}: {
  run: ProgrammingRun;
  onAcknowledge?: () => void;
  acknowledging?: boolean;
  ariaLabel?: string;
  /** Site interface the PPU reported (e.g. "openocd", "mock"); tells a Mock result from hardware. */
  executionInterface?: string | null;
}) {
  const { verdict, reason } = runVerdict(run);
  const progress = runProgressPercent(run);
  const receipt = run.receipt;
  // Diagnostics need a complete Manager plan record.
  const plan = run.plan?.plan_id && run.plan.route && run.plan.job_binding ? run.plan : null;
  const hex = (value: number) => `0x${value.toString(16).toUpperCase().padStart(8, "0")}`;
  const steps = receipt?.operations ?? [];
  return (
    <section aria-label={ariaLabel} className="ppuSiteCard programmingRunView">
      <h4 data-testid="run-outcome" data-run-verdict={verdict}>{verdictLabel(run, verdict)}</h4>
      {reason && <p data-testid="run-reason">Reason: {reason}</p>}
      <p data-testid="run-policy">
        Run {run.run_id} · PPU {run.ppu_alias} · Site {run.site_id} · attempts {run.job_submission_count} · auto retry {run.auto_retry}
      </p>
      {executionInterface !== undefined && (
        <p data-testid="run-evidence" data-run-evidence={executionInterface === "mock" ? "mock" : "ppu"}>
          {executionInterface === "mock"
            ? "MOCK RESULT · Site interface mock · not hardware evidence and never a hardware qualification"
            : `Site interface: ${executionInterface ?? "not reported"}`}
        </p>
      )}
      <ol aria-label="Programming steps">
        {run.steps.map((step, index) => <li key={`${step.step}-${index}`}>{step.step}: {step.result}</li>)}
      </ol>
      {run.job && (
        <p data-testid="run-job">
          Job {run.job.job_id ?? "—"} · {run.job.state ?? "—"}
          {progress != null ? ` · ${progress}%` : ""}
        </p>
      )}
      {receipt && (
        <dl aria-label="Programming receipt">
          <dt>Job ID</dt><dd data-testid="receipt-job"><code>{receipt.job_id ?? "—"}</code></dd>
          <dt>Operations</dt>
          <dd data-testid="receipt-operations">
            {receipt.operations ? receipt.operations.join(" → ") : receipt.operation ?? "—"}
            {receipt.operations && ` (one Job · PPU ran: ${receipt.observed_operations?.join(" → ") ?? "not reported"})`}
          </dd>
          {steps.map(step => (
            <div key={step} style={{ display: "contents" }}>
              <dt>{step[0].toUpperCase() + step.slice(1)} evidence</dt>
              <dd data-testid={`receipt-step-${step}`}>
                <code>{JSON.stringify(receipt.observed_steps?.[step] ?? null)}</code>
              </dd>
            </div>
          ))}
          <dt>Range</dt><dd data-testid="receipt-range">{receipt.range ? `${hex(receipt.range.address)} + ${receipt.range.length} B` : "—"}</dd>
          <dt>Expected Image</dt><dd><code>{receipt.expected_image_sha256 ?? "—"}</code></dd>
          <dt>PPU Observed Image</dt><dd><code>{receipt.observed_image_sha256 ?? "—"}</code></dd>
          <dt>Readback SHA256</dt><dd data-testid="receipt-readback"><code>{receipt.readback_sha256 ?? "—"}</code></dd>
          <dt>Verified Bytes</dt><dd data-testid="receipt-bytes">{receipt.bytes_verified ?? "—"} / {receipt.expected_image_size ?? "—"}</dd>
          <dt>Resources</dt>
          <dd data-testid="receipt-resource">{receipt.resource_reuse ? "Reused" : "Activated"}</dd>
          <dt>Resource SHA256</dt>
          <dd data-testid="receipt-resource-sha"><code>{receipt.observed_resource_set_sha256 ?? "—"}</code></dd>
          <dt>Job Binding SHA256</dt>
          <dd data-testid="receipt-binding-sha"><code>{receipt.observed_job_binding_sha256 ?? "—"}</code></dd>
          <dt>SAFE_OFF</dt><dd data-testid="receipt-safe-off">{receipt.safe_off === true ? "VERIFIED" : "NOT VERIFIED"}</dd>
        </dl>
      )}
      {plan && (
        <dl aria-label="Programming plan diagnostics" data-testid="run-plan-diagnostics">
          <dt>Plan ID</dt><dd data-testid="plan-id"><code>{plan.plan_id}</code></dd>
          <dt>Route</dt><dd data-testid="plan-route">{plan.route.route_id} ({plan.route.provider} → {plan.route.profile})</dd>
          <dt>Source</dt><dd data-testid="plan-source">{plan.source}</dd>
          <dt>Planned Operations</dt><dd data-testid="plan-operation">{(plan.operations ?? [plan.operation]).join(" → ")}</dd>
          <dt>Planned Range</dt><dd>{hex(plan.job_binding.range.address)} + {plan.job_binding.range.length} B</dd>
          <dt>Plan Resource SHA256</dt><dd data-testid="plan-resource-sha"><code>{plan.resource.resource_set_sha256}</code></dd>
          <dt>Plan Job Binding SHA256</dt><dd data-testid="plan-binding-sha"><code>{plan.job_binding_sha256}</code></dd>
          <dt>Resources</dt>
          <dd data-testid="plan-activation">
            {plan.activation_required
              ? "Activation: B1 upload → B2 admit → B3 activate (no FPGA load)"
              : "Resource Reuse: the PPU verified identical Programming Resources (no B1/B2/B3, no FPGA load)"}
          </dd>
        </dl>
      )}
      {run.outcome === "OUTCOME_UNKNOWN" && (
        <div role="alert" className="ppuRegistryMessage error">
          <p>
            The device-side outcome is unknown. Nothing was resubmitted. Reconcile the PPU Job/Bootstrap state
            (and any SEALED Site) through the normal recovery procedure before programming this PPU again.
          </p>
          {!run.acknowledged && onAcknowledge && (
            <button className="ppuSiteButton" type="button" disabled={acknowledging} onClick={onAcknowledge}>
              Acknowledge reconciliation
            </button>
          )}
        </div>
      )}
    </section>
  );
}
