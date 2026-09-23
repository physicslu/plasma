"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ManagerRegistryEntry } from "./ppu-registry-api";
import {
  appendManagerPpuBootstrapChunk,
  bytesToBase64,
  commitManagerPpuBootstrapUpload,
  createManagerPpuBootstrapUpload,
  getManagerPpuBootstrap,
  pairManagerPpuBootstrap,
  parseSha256Sidecar,
  runManagerPpuPlatformPsLoopback,
  sha256Hex,
  startManagerPpuBootstrapDeployment,
  type ManagerBootstrapStatus,
  type PlatformPsLoopbackPayload,
} from "./ppu-bootstrap-api";

const CHUNK_BYTES = 1024 * 1024;

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
  hasTrustedIdleObservation: boolean;
};

function stateLabel(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return value.replaceAll("_", " ");
}

function platformReleaseIdentity(status: ManagerBootstrapStatus | null): string {
  if (status?.bootstrap.runtime.release_id) return status.bootstrap.runtime.release_id;
  if (status?.bootstrap.bootstrap.state === "bootstrap_ready") return "Bootstrap only";
  return "Unavailable";
}

export default function PpuRuntimeDeployment({
  entry,
  hasActiveExecution,
  hasTrustedIdleObservation,
}: Props) {
  const alias = entry.alias ?? "";
  const [status, setStatus] = useState<ManagerBootstrapStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"pair" | "deploy" | "loopback" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pairingToken, setPairingToken] = useState("");
  const [kit, setKit] = useState<File | null>(null);
  const [sidecar, setSidecar] = useState<File | null>(null);
  const [ppuId, setPpuId] = useState(alias);
  const [facilityId, setFacilityId] = useState("lab");
  const [displayName, setDisplayName] = useState(alias || "Plasma PPU");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [loopback, setLoopback] = useState<PlatformPsLoopbackPayload | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    if (!alias) return;
    if (!quiet) setLoading(true);
    try {
      const next = await getManagerPpuBootstrap(alias);
      setStatus(next);
      setError(null);
      const identity = next.bootstrap.identity;
      if (identity.ppu_id) setPpuId(current => current || identity.ppu_id || alias);
      if (identity.facility_id) setFacilityId(current => current || identity.facility_id || "lab");
    } catch (reason) {
      setStatus(null);
      if (!quiet) setError(reason instanceof Error ? reason.message : "PPU Bootstrap unavailable");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [alias]);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(true); }, 3000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const bootstrap = status?.bootstrap ?? null;
  const pairing = status?.pairing ?? null;
  const runtime = bootstrap?.runtime ?? null;
  const deployment = bootstrap?.deployment ?? null;
  const recoveryRequired = runtime?.state === "recovery_required" || deployment?.state === "recovery_required";
  const firstInstall = runtime?.state === "runtime_absent";
  const maintenanceReady = firstInstall || (runtime?.state === "runtime_active" && hasTrustedIdleObservation);
  const canPair = Boolean(alias && pairingToken.trim().length >= 32 && busy === null);
  const canLoopback = Boolean(
    alias
    && pairing?.paired
    && pairing.device_match
    && runtime?.state === "runtime_active"
    && busy === null,
  );
  const canDeploy = Boolean(
    alias
    && maintenanceReady
    && pairing?.paired
    && pairing.device_match
    && bootstrap?.capabilities.runtime_deployment
    && kit
    && sidecar
    && ppuId.trim()
    && facilityId.trim()
    && displayName.trim()
    && !hasActiveExecution
    && !recoveryRequired
    && busy === null
    && deployment?.state !== "queued"
    && deployment?.state !== "running",
  );
  const deploymentTone = useMemo(() => {
    if (!deployment) return "neutral";
    if (deployment.state === "succeeded") return "success";
    if (deployment.state === "failed" || deployment.state === "recovery_required") return "danger";
    return "warning";
  }, [deployment]);

  async function pair() {
    if (!canPair) return;
    setBusy("pair");
    setError(null);
    setNotice(null);
    try {
      await pairManagerPpuBootstrap(alias, pairingToken);
      setPairingToken("");
      setNotice("Platform maintenance credential stored for this PPU. Maintenance authorization is active for the bounded Platform workflow.");
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Platform maintenance pairing failed");
    } finally {
      setBusy(null);
    }
  }

  async function runLoopback() {
    if (!canLoopback) return;
    setBusy("loopback");
    setError(null);
    setNotice(null);
    setLoopback(null);
    try {
      const result = await runManagerPpuPlatformPsLoopback(alias);
      setLoopback(result);
      setNotice("Platform PS Loop Test passed through the active Runtime.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Platform PS Loop Test failed");
    } finally {
      setBusy(null);
    }
  }

  async function deploy() {
    if (!canDeploy || !kit || !sidecar) return;
    setBusy("deploy");
    setError(null);
    setNotice(null);
    setLoopback(null);
    setUploadProgress(0);
    try {
      const sidecarText = await sidecar.text();
      const expected = parseSha256Sidecar(sidecarText, kit.name);
      const wholeDigest = await sha256Hex(await kit.arrayBuffer());
      if (wholeDigest !== expected) throw new Error("Selected PPU Platform Release package SHA-256 does not match its sidecar");

      const created = await createManagerPpuBootstrapUpload(alias, kit.size, expected);
      let offset = 0;
      while (offset < kit.size) {
        const bytes = new Uint8Array(await kit.slice(offset, Math.min(offset + CHUNK_BYTES, kit.size)).arrayBuffer());
        const chunkDigest = await sha256Hex(bytes);
        await appendManagerPpuBootstrapChunk(alias, created.upload.upload_id, offset, bytesToBase64(bytes), chunkDigest);
        offset += bytes.byteLength;
        setUploadProgress(Math.round((offset / kit.size) * 100));
      }
      await commitManagerPpuBootstrapUpload(alias, created.upload.upload_id);
      await startManagerPpuBootstrapDeployment(alias, {
        upload_id: created.upload.upload_id,
        ppu_id: ppuId.trim(),
        facility_id: facilityId.trim(),
        display_name: displayName.trim(),
      });
      setNotice("PPU Platform Release update accepted by Bootstrap. Deployment status will continue updating asynchronously.");
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "PPU Platform Release update failed");
    } finally {
      setUploadProgress(null);
      setBusy(null);
    }
  }

  return (
    <section className="ppuSiteCard ppuPlatformCard" aria-label="PPU Platform Release">
      <header className="ppuSiteCardHeader ppuPlatformSummaryHeader">
        <div>
          <small>PLATFORM SUMMARY</small>
          <h3>Current platform state</h3>
          <p>Bootstrap, Runtime, device identity, and maintenance authorization for the selected PPU.</p>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading || busy !== null} onClick={() => void refresh()}>
          {loading ? "Checking..." : "Refresh Platform Status"}
        </button>
      </header>

      {error && (
        <div className="ppuPlatformAlert" data-tone="danger" role="alert">
          <strong>Platform status unavailable</strong>
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="ppuPlatformAlert" data-tone="success" role="status">
          <strong>Platform workflow updated</strong>
          <span>{notice}</span>
        </div>
      )}
      {hasActiveExecution && <p className="ppuRegistryMessage warning" role="status">Platform Release update is blocked while this PPU has active Site execution.</p>}
      {runtime?.state === "runtime_active" && !hasTrustedIdleObservation && <p className="ppuRegistryMessage warning" role="status">Normal Platform maintenance requires a current trusted idle PPU observation. Programming Registration does not control this Platform gate. If Runtime health cannot be observed, use the explicit recovery procedure.</p>}
      {recoveryRequired && <p className="ppuRegistryMessage error" role="alert">Recovery required. Normal Platform Release update remains blocked until the interrupted or unsafe PPU state is explicitly recovered.</p>}

      <section className="ppuPlatformSection" aria-labelledby="platform-summary-heading">
        <header className="ppuPlatformSectionHeader">
          <div>
            <small>STATUS</small>
            <h4 id="platform-summary-heading">Platform Summary</h4>
          </div>
          <span className="ppuPlatformStatusPill" data-tone={pairing?.paired && pairing.device_match ? "success" : "warning"}>
            {pairing?.paired && pairing.device_match ? "Maintenance paired" : "Maintenance required"}
          </span>
        </header>
        <dl className="ppuPlatformSummaryGrid">
          <div className="ppuPlatformMetric">
            <dt>Platform Release</dt>
            <dd>{platformReleaseIdentity(status)}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Runtime State</dt>
            <dd>{stateLabel(runtime?.state)}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Runtime Version</dt>
            <dd>{runtime?.product_version ?? "Not installed"}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Bootstrap State</dt>
            <dd>{stateLabel(bootstrap?.bootstrap.state)}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Bootstrap Version</dt>
            <dd>{bootstrap?.bootstrap.version ?? "Unavailable"}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Runtime Commit</dt>
            <dd className="ppuPlatformMonoValue">{runtime?.git_sha ?? "—"}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Device ID</dt>
            <dd className="ppuPlatformMonoValue">{bootstrap?.identity.device_id ?? "Unavailable"}</dd>
          </div>
          <div className="ppuPlatformMetric">
            <dt>Maintenance Authorization</dt>
            <dd>{pairing?.paired && pairing.device_match ? "Paired" : "Required"}</dd>
          </div>
        </dl>
      </section>

      <div className="ppuPlatformActionGrid">
        <section className="ppuPlatformSection ppuPlatformMaintenance" aria-labelledby="platform-maintenance-heading">
          <header className="ppuPlatformSectionHeader">
            <div>
              <small>MAINTENANCE</small>
              <h4 id="platform-maintenance-heading">Platform Maintenance</h4>
              <p>Authorize maintenance independently from programming Registration.</p>
            </div>
          </header>
          <div className="ppuPlatformMaintenanceControls">
            <label className="operatorField">
              <span>Platform Maintenance Pairing Token</span>
              <input
                type="password"
                autoComplete="off"
                value={pairingToken}
                disabled={busy !== null}
                placeholder="Factory / recovery pairing token"
                onChange={event => setPairingToken(event.target.value)}
              />
            </label>
            <button className="operatorButton" type="button" disabled={!canPair} onClick={() => void pair()}>
              {busy === "pair" ? "Pairing..." : "Authorize Platform Maintenance"}
            </button>
          </div>
          <p className="ppuPlatformSectionNote">This credential authorizes Platform maintenance. It does not register the PPU for managed programming operations.</p>
        </section>

        <section className="ppuPlatformSection ppuPlatformLoopback" aria-labelledby="platform-loopback-heading">
          <div className="ppuPlatformLoopbackAction">
            <header className="ppuPlatformSectionHeader">
              <div>
                <small>DIAGNOSTIC</small>
                <h4 id="platform-loopback-heading">Platform PS Loop Test</h4>
                <p>Runs the active Runtime PS loopback through the Platform maintenance admission path. Programming Registration is not required.</p>
              </div>
            </header>
            <button className="operatorButton" data-variant="primary" type="button" disabled={!canLoopback} onClick={() => void runLoopback()}>
              {busy === "loopback" ? "Testing PS..." : "Run PS Loop Test"}
            </button>
            {!pairing?.paired && <p className="ppuPlatformSectionNote">Platform maintenance pairing is required before this diagnostic can run.</p>}
            {pairing?.paired && runtime?.state !== "runtime_active" && <p className="ppuPlatformSectionNote">The Runtime must be active before PS Loop Test can run.</p>}
          </div>

          <aside className="ppuPlatformLoopbackResult" aria-label="Platform PS Loop Test result" data-state={loopback ? "pass" : "empty"}>
            {loopback ? (
              <>
                <header>
                  <span className="ppuPlatformStatusPill" data-tone="success">PASS</span>
                  <strong>Loop Test Result</strong>
                </header>
                <dl>
                  <div><dt>PPU RTT</dt><dd>{loopback.loopback.ppu_rtt_ms ?? "—"} ms</dd></div>
                  <div><dt>Manager RTT</dt><dd>{loopback.manager.manager_rtt_ms} ms</dd></div>
                  <div><dt>Context</dt><dd>{loopback.manager.context}</dd></div>
                  <div><dt>Source</dt><dd>{loopback.loopback.source}</dd></div>
                  <div className="wide"><dt>Test ID</dt><dd>{loopback.loopback.test_id}</dd></div>
                </dl>
              </>
            ) : (
              <div className="ppuPlatformLoopbackEmpty">
                <strong>No test result yet</strong>
                <span>{!pairing?.paired ? "Platform maintenance pairing is required before this diagnostic can run." : "Run the PS Loop Test to capture diagnostic evidence."}</span>
              </div>
            )}
          </aside>
        </section>
      </div>

      <section className="ppuPlatformSection ppuPlatformRuntimeDeployment" aria-labelledby="platform-runtime-deployment-heading">
        <header className="ppuPlatformSectionHeader">
          <div>
            <small>RUNTIME DEPLOYMENT</small>
            <h4 id="platform-runtime-deployment-heading">Runtime Deployment</h4>
            <p>Upload and deploy Platform Runtime components through the installed Bootstrap.</p>
          </div>
        </header>
        <div className="ppuPlatformDeploymentForm">
          <label className="operatorField ppuPlatformFileField">
            <span>PPU Platform Release Package</span>
            <input type="file" disabled={busy !== null} onChange={event => setKit(event.target.files?.[0] ?? null)} />
          </label>
          <label className="operatorField ppuPlatformFileField">
            <span>SHA-256 Sidecar</span>
            <input type="file" disabled={busy !== null} onChange={event => setSidecar(event.target.files?.[0] ?? null)} />
          </label>
          <label className="operatorField">
            <span>PPU ID</span>
            <input value={ppuId} disabled={busy !== null} onChange={event => setPpuId(event.target.value)} />
          </label>
          <label className="operatorField">
            <span>Facility ID</span>
            <input value={facilityId} disabled={busy !== null} onChange={event => setFacilityId(event.target.value)} />
          </label>
          <label className="operatorField ppuPlatformDisplayNameField">
            <span>Display Name</span>
            <input value={displayName} disabled={busy !== null} onChange={event => setDisplayName(event.target.value)} />
          </label>
          <button className="operatorButton ppuPlatformDeployButton" data-variant="primary" type="button" disabled={!canDeploy} onClick={() => void deploy()}>
            {busy === "deploy" ? `Updating${uploadProgress == null ? "" : ` ${uploadProgress}%`}` : "Update PPU Platform Release"}
          </button>
        </div>
        <p className="ppuPlatformSectionNote">
          The current qualified update authority deploys the Runtime component through the installed Bootstrap and preserves existing rollback/recovery gates. Bootstrap remains independently versioned and is not silently rewritten by this path. Programming Logic, including FPGA bitstreams and ICPN-selected Python logic, is a separate lifecycle.
        </p>
      </section>

      <section className="ppuPlatformDeploymentStatus" aria-label="Platform deployment status" data-tone={deploymentTone}>
        <div>
          <small>PLATFORM DEPLOYMENT</small>
          <strong>{stateLabel(deployment?.state)}</strong>
        </div>
        <div>
          <small>TRANSACTION</small>
          <span className="ppuPlatformMonoValue">{deployment?.transaction_id ?? "No deployment transaction"}</span>
        </div>
        {deployment?.error && <p className="ppuRegistryMessage error">{deployment.error}</p>}
      </section>
    </section>
  );
}
