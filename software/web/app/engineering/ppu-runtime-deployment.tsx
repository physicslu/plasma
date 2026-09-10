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
    setStatus(null);
    setPairingToken("");
    setKit(null);
    setSidecar(null);
    setPpuId(alias);
    setFacilityId("lab");
    setDisplayName(alias || "Plasma PPU");
    setUploadProgress(null);
    setNotice(null);
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { void refresh(true); }, 3000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [alias, refresh]);

  const bootstrap = status?.bootstrap ?? null;
  const pairing = status?.pairing ?? null;
  const runtime = bootstrap?.runtime ?? null;
  const deployment = bootstrap?.deployment ?? null;
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
    && busy === null
    && deployment?.state !== "queued"
    && deployment?.state !== "running",
  );
  const deploymentTone = useMemo(() => {
    if (!deployment) return "neutral";
    if (deployment.state === "succeeded") return "success";
    if (deployment.state === "failed") return "danger";
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
      setNotice("Bootstrap pairing credential is now owned by Manager. The browser copy was cleared.");
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
      const expectedSha = parseSha256Sidecar(await sidecar.text(), kit.name);
      const created = await createManagerPpuBootstrapUpload(alias, kit.size, expectedSha);
      const uploadId = created.upload.upload_id;
      let offset = 0;
      while (offset < kit.size) {
        const end = Math.min(offset + CHUNK_BYTES, kit.size);
        const buffer = await kit.slice(offset, end).arrayBuffer();
        const chunkSha = await sha256Hex(buffer);
        await appendManagerPpuBootstrapChunk(
          alias,
          uploadId,
          offset,
          bytesToBase64(buffer),
          chunkSha,
        );
        offset = end;
        setUploadProgress(Math.round((offset / kit.size) * 100));
      }
      await commitManagerPpuBootstrapUpload(alias, uploadId);
      await startManagerPpuBootstrapDeployment(alias, {
        upload_id: uploadId,
        ppu_id: ppuId.trim(),
        facility_id: facilityId.trim(),
        display_name: displayName.trim(),
      });
      setNotice("Verified kit upload committed. PPU Bootstrap deployment has started asynchronously.");
      await refresh(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Runtime deployment failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="PPU Runtime Deployment">
      <header className="ppuSiteCardHeader">
        <div>
          <small>APPLIANCE LIFECYCLE</small>
          <h3>PPU Runtime Deployment</h3>
          <p>Console declares the desired runtime; Manager controls the device-bound credential; PPU Bootstrap performs installation and recovery.</p>
        </div>
        <div className="ppuSiteCardHeaderActions">
          <span className="ppuSiteFilter">Bootstrap {bootstrap?.bootstrap.state ?? (loading ? "checking" : "unavailable")}</span>
          <button className="ppuSiteButton" type="button" disabled={busy !== null} onClick={() => void refresh()}>Refresh</button>
        </div>
      </header>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}
      {notice && <p className="ppuRegistryMessage success" role="status">{notice}</p>}

      {bootstrap ? (
        <>
          <div className="ppuInfoBody">
            <dl className="ppuInfoGrid">
              <div><dt>Bootstrap</dt><dd>{bootstrap.bootstrap.version} / {stateLabel(bootstrap.bootstrap.state)}</dd></div>
              <div><dt>Device ID</dt><dd>{bootstrap.identity.device_id}</dd></div>
              <div><dt>Pairing</dt><dd>{pairing?.paired && pairing.device_match ? "Paired / device matched" : pairing?.paired ? "Device mismatch" : "Not paired"}</dd></div>
              <div><dt>Runtime</dt><dd>{stateLabel(runtime?.state)}</dd></div>
              <div><dt>Runtime Version</dt><dd>{runtime?.product_version ?? "Not installed"}</dd></div>
              <div><dt>Release ID</dt><dd>{runtime?.release_id ?? "—"}</dd></div>
              <div><dt>Hardware Revision</dt><dd>{bootstrap.identity.hardware_revision ?? "Not provisioned"}</dd></div>
              <div><dt>FPGA Image</dt><dd>{bootstrap.fpga.pl_version ?? "Not managed"}</dd></div>
              <div><dt>PL Qualification</dt><dd>{stateLabel(bootstrap.fpga.pl_qualification)}</dd></div>
              <div><dt>FPGA Update</dt><dd>{bootstrap.capabilities.fpga_update ? "Supported" : "Reserved / disabled"}</dd></div>
            </dl>
          </div>

          {!pairing?.paired || pairing.device_match === false ? (
            <div className="ppuRegistryAddForm" aria-label="Pair PPU Bootstrap">
              <label>
                <span>One-time Bootstrap Pairing Token</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={pairingToken}
                  disabled={busy !== null || entry.lifecycle === "commissioned"}
                  onChange={event => setPairingToken(event.target.value)}
                  placeholder="Enter factory/recovery token"
                />
              </label>
              <div className="ppuSiteCardHeaderActions">
                <button className="ppuSiteButton primary" type="button" disabled={!canPair} onClick={() => void pair()}>
                  {busy === "pair" ? "Pairing..." : "Pair Bootstrap"}
                </button>
              </div>
              <p>
                {entry.lifecycle === "commissioned"
                  ? "Disable this PPU before changing Bootstrap pairing. Existing commissioned credentials cannot be silently replaced."
                  : "The token is sent once through the same-origin BFF to Manager, persisted there as a device-bound secret, then cleared from browser state."}
              </p>
            </div>
          ) : (
            <div className="ppuRegistryAddForm" aria-label="Deploy Plasma Runtime">
              <label>
                <span>Canonical Z2 PS Kit</span>
                <input type="file" accept=".gz,application/gzip" disabled={busy !== null} onChange={event => setKit(event.target.files?.[0] ?? null)} />
              </label>
              <label>
                <span>Detached SHA-256 Sidecar</span>
                <input type="file" accept=".sha256,text/plain" disabled={busy !== null} onChange={event => setSidecar(event.target.files?.[0] ?? null)} />
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
              <div className="ppuSiteCardHeaderActions">
                <button className="ppuSiteButton primary" type="button" disabled={!canDeploy} onClick={() => void deploy()}>
                  {busy === "deploy" ? `Uploading ${uploadProgress ?? 0}%...` : runtime?.state === "runtime_active" ? "Deploy / Upgrade Runtime" : "Install Runtime"}
                </button>
              </div>
              <p>Upload is 1 MiB chunked with per-chunk SHA-256 and final artifact SHA-256. SHA-256 proves integrity only; publisher authenticity remains a production-hardening requirement.</p>
              {hasActiveExecution && <p className="ppuRegistryMessage warning">Runtime deployment is blocked while any Site has an active Job.</p>}
            </div>
          )}

          <div className="ppuStateDimensionGrid" aria-label="Runtime deployment status">
            <article className="ppuStateDimensionCard" data-tone={deploymentTone}>
              <small>Deployment</small>
              <strong>{deployment ? stateLabel(deployment.state) : "No transaction"}</strong>
              <p>{deployment?.error ?? (deployment ? `Transaction ${deployment.transaction_id}` : "No Bootstrap deployment has been recorded.")}</p>
            </article>
            <article className="ppuStateDimensionCard" data-tone="neutral">
              <small>Transport Security</small>
              <strong>{stateLabel(bootstrap.security?.transport_confidentiality)}</strong>
              <p>Phase 3 is limited to the controlled private commissioning link. TLS/mTLS is not yet qualified.</p>
            </article>
            <article className="ppuStateDimensionCard" data-tone="neutral">
              <small>Publisher Authenticity</small>
              <strong>{stateLabel(bootstrap.security?.publisher_authenticity)}</strong>
              <p>Release signing is intentionally deferred to production hardening; no authenticity claim is made here.</p>
            </article>
          </div>
        </>
      ) : (
        <div className="ppuDiscoveredBody">
          <p className="ppuSiteNote">Bootstrap status is unavailable. Runtime deployment remains fail-closed; the normal Plasma Gateway path is not used as a fallback.</p>
        </div>
      )}
    </section>
  );
}
