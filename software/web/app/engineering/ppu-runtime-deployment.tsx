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
  sha256Hex,
  startManagerPpuBootstrapDeployment,
  type ManagerBootstrapStatus,
} from "./ppu-bootstrap-api";

const CHUNK_BYTES = 1024 * 1024;

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

function stateLabel(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return value.replaceAll("_", " ");
}

export default function PpuRuntimeDeployment({ entry, hasActiveExecution }: Props) {
  const alias = entry.alias ?? "";
  const [status, setStatus] = useState<ManagerBootstrapStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"pair" | "deploy" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pairingToken, setPairingToken] = useState("");
  const [kit, setKit] = useState<File | null>(null);
  const [sidecar, setSidecar] = useState<File | null>(null);
  const [ppuId, setPpuId] = useState(alias);
  const [facilityId, setFacilityId] = useState("lab");
  const [displayName, setDisplayName] = useState(alias || "Plasma PPU");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);

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
  const canPair = Boolean(
    alias
    && pairingToken.trim().length >= 32
    && entry.lifecycle !== "commissioned"
    && !hasActiveExecution
    && busy === null,
  );
  const canDeploy = Boolean(
    alias
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
      setNotice("Bootstrap pairing stored by Manager for this immutable device identity.");
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Bootstrap pairing failed");
    } finally {
      setBusy(null);
    }
  }

  async function deploy() {
    if (!canDeploy || !kit || !sidecar) return;
    setBusy("deploy");
    setError(null);
    setNotice(null);
    setUploadProgress(0);
    try {
      const sidecarText = await sidecar.text();
      const expected = parseSha256Sidecar(sidecarText, kit.name);
      const wholeDigest = await sha256Hex(await kit.arrayBuffer());
      if (wholeDigest !== expected) throw new Error("Selected kit SHA256 does not match its sidecar");

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
      setNotice("Runtime deployment accepted by PPU Bootstrap. Status will continue updating asynchronously.");
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Runtime deployment failed");
    } finally {
      setUploadProgress(null);
      setBusy(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="PPU Runtime Deployment">
      <header className="ppuSiteCardHeader">
        <div>
          <small>FACTORY / RECOVERY</small>
          <h3>Runtime Deployment</h3>
        </div>
        <button className="ppuSiteButton" type="button" disabled={loading || busy !== null} onClick={() => void refresh()}>
          {loading ? "Checking..." : "Refresh Bootstrap"}
        </button>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}
      {hasActiveExecution && <p className="ppuRegistryMessage warning" role="status">Runtime deployment is blocked while this PPU has active Site execution.</p>}
      {recoveryRequired && <p className="ppuRegistryMessage error" role="alert">Recovery required. Normal Runtime deployment remains blocked until the interrupted or unsafe PPU state is explicitly recovered.</p>}

      <div className="ppuInfoBody">
        <dl className="ppuInfoGrid">
          <div><dt>Bootstrap</dt><dd>{stateLabel(bootstrap?.bootstrap.state)}</dd></div>
          <div><dt>Device ID</dt><dd>{bootstrap?.identity.device_id ?? "Unavailable"}</dd></div>
          <div><dt>Runtime</dt><dd>{stateLabel(runtime?.state)}</dd></div>
          <div><dt>Runtime Version</dt><dd>{runtime?.product_version ?? "Not installed"}</dd></div>
          <div><dt>Pairing</dt><dd>{pairing?.paired && pairing.device_match ? "Paired" : "Required"}</dd></div>
          <div><dt>Runtime Deployment</dt><dd>{bootstrap?.capabilities.runtime_deployment ? "Available" : "Unavailable"}</dd></div>
          <div><dt>FPGA Image</dt><dd>{stateLabel(bootstrap?.fpga.pl_compatibility)}</dd></div>
          <div><dt>FPGA Update</dt><dd>{bootstrap?.capabilities.fpga_update ? "Available" : "Reserved / Disabled"}</dd></div>
        </dl>
      </div>

      <div className="ppuRegistryAddForm" aria-label="Bootstrap pairing">
        <label>
          <span>Bootstrap Pairing Token</span>
          <input
            type="password"
            autoComplete="off"
            value={pairingToken}
            disabled={entry.lifecycle === "commissioned" || hasActiveExecution || busy !== null}
            placeholder="Factory pairing token"
            onChange={event => setPairingToken(event.target.value)}
          />
        </label>
        <button className="ppuSiteButton" type="button" disabled={!canPair} onClick={() => void pair()}>
          {busy === "pair" ? "Pairing..." : "Pair Bootstrap"}
        </button>
        {entry.lifecycle === "commissioned" && <p>Disable this commissioned PPU before rotating or replacing its Bootstrap pairing.</p>}
      </div>

      <div className="ppuRegistryAddForm" aria-label="Runtime release deployment">
        <label>
          <span>Z2 PS Kit</span>
          <input type="file" disabled={busy !== null} onChange={event => setKit(event.target.files?.[0] ?? null)} />
        </label>
        <label>
          <span>SHA256 Sidecar</span>
          <input type="file" disabled={busy !== null} onChange={event => setSidecar(event.target.files?.[0] ?? null)} />
        </label>
        <label>
          <span>PPU ID</span>
          <input value={ppuId} disabled={busy !== null} onChange={event => setPpuId(event.target.value)} />
        </label>
        <label>
          <span>Facility ID</span>
          <input value={facilityId} disabled={busy !== null} onChange={event => setFacilityId(event.target.value)} />
        </label>
        <label>
          <span>Display Name</span>
          <input value={displayName} disabled={busy !== null} onChange={event => setDisplayName(event.target.value)} />
        </label>
        <button className="ppuSiteButton primary" type="button" disabled={!canDeploy} onClick={() => void deploy()}>
          {busy === "deploy" ? `Uploading${uploadProgress == null ? "" : ` ${uploadProgress}%`}` : "Deploy Runtime"}
        </button>
        <p>Console uploads a SHA-256-verified Z2 PS kit through Manager. Bootstrap validates immutable release identity and owns activation plus automatic rollback on failed activation. Publisher signature verification remains a production-hardening requirement; FPGA bitstream loading is not enabled in this project.</p>
      </div>

      <div className="ppuReadinessPanel" aria-label="Deployment status">
        <header>
          <div>
            <small>DEPLOYMENT</small>
            <h4>{stateLabel(deployment?.state)}</h4>
          </div>
          <span data-tone={deploymentTone}>{deployment?.transaction_id ?? "No deployment transaction"}</span>
        </header>
        {deployment?.error && <p className="ppuRegistryMessage error">{deployment.error}</p>}
      </div>
    </section>
  );
}
