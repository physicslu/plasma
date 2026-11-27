"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { DeviceSearchResult } from "../device-catalog-api";
import { ICPickerField } from "../devices/ic-picker-field";
import {
  loadManagedTopology, runManagedBatch, runManagedRead, type ManagedTopology,
} from "../programming/managed-programming";
import { ProgrammingRunView } from "../operator-ui/programming-run-view";
import {
  acknowledgeProgrammingRun,
  getProgrammingRoutes,
  IMAGE_OPERATIONS,
  PROGRAMMING_OPERATIONS,
  type ProgrammingRoute,
  type ProgrammingRun,
} from "./bundle-programming-api";

// The IC Profile determines programming support; the PPU determines which Sites exist.
const PICKER_LEVELS: Array<1 | 2 | 3> = [1, 2, 3];

export default function BundleProgramming({ alias }: { alias: string }) {
  const [routes, setRoutes] = useState<ProgrammingRoute[] | null>(null);
  const [topology, setTopology] = useState<ManagedTopology | null>(null);
  const [routesError, setRoutesError] = useState<string | null>(null);
  const [device, setDevice] = useState<DeviceSearchResult | null>(null);
  const [chosenSite, setChosenSite] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [chosenOperation, setChosenOperation] = useState<string | null>(null);
  const [rangeAddress, setRangeAddress] = useState("");
  const [rangeLength, setRangeLength] = useState("");
  const [confirmedKey, setConfirmedKey] = useState<string | null>(null);
  const [run, setRun] = useState<ProgrammingRun | null>(null);
  const [busy, setBusy] = useState<"start" | "ack" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    getProgrammingRoutes(alias)
      .then(next => { if (!cancelled) { setRoutes(next); setRoutesError(null); } })
      .catch(reason => {
        if (!cancelled) setRoutesError(reason instanceof Error ? reason.message : "Programming Routes unavailable");
      });
    loadManagedTopology().then(next => { if (!cancelled) setTopology(next); })
      .catch(reason => { if (!cancelled) setRoutesError(reason instanceof Error ? reason.message : "PPU Site topology unavailable"); });
    return () => { cancelled = true; };
  }, [alias]);

  const icpn = device?.icpn ?? device?.identifier ?? null;
  const siteOptions = useMemo(() => {
    const ppu = topology?.ppus.find(item => item.alias === alias);
    if (!ppu?.online) return [];
    return ppu.sites.filter(site => site.enabled && site.state === "idle"
      && (site.interface === "openocd" || site.interface === "fpga"))
      .map(site => site.site_id).sort((a, b) => a - b);
  }, [alias, topology]);

  const siteId = chosenSite != null && siteOptions.includes(chosenSite) ? chosenSite : siteOptions[0] ?? null;
  // Offer only Operations the matching Route Profile declares; the user picks one.
  const operationOptions = useMemo(() => {
    if (!icpn || !routes || siteId == null) return [];
    const declared = new Set(routes
      .filter(route => route.icpn === icpn)
      .flatMap(route => route.operations));
    return PROGRAMMING_OPERATIONS.filter(operation => operation === "programming"
      ? ["erase", "program", "verify"].every(step => declared.has(step))
      : declared.has(operation));
  }, [icpn, routes, siteId]);
  const operation = chosenOperation != null && (operationOptions as readonly string[]).includes(chosenOperation)
    ? chosenOperation
    : operationOptions[0] ?? null;
  const needsImage = operation != null && IMAGE_OPERATIONS.has(operation);
  const address = /^(0x[0-9a-f]+|[0-9]+)$/i.test(rangeAddress.trim()) ? Number(rangeAddress.trim()) : null;
  const length = /^(0x[0-9a-f]+|[0-9]+)$/i.test(rangeLength.trim()) ? Number(rangeLength.trim()) : null;
  // The confirmation is valid only for the exact selection it was given for.
  const selectionKey = `${alias}|${icpn ?? ""}|${siteId ?? ""}|${operation ?? ""}|${needsImage
    ? (file ? `${file.name}:${file.size}:${file.lastModified}` : "")
    : `${address ?? ""}:${length ?? ""}`}`;
  const confirmed = confirmedKey === selectionKey;

  const inputReady = needsImage ? file != null : address != null && length != null;
  const ready = Boolean(icpn && siteId != null && operation && inputReady && !busy);
  const canStart = ready && confirmed;

  /**
   * One Manager Batch of one Site and one Cycle (U2): the same canonical
   * Batch EMode and PMode use. The Manager reuses or activates Resources
   * before its Reservation and submits the Job once; nothing is retried.
   */
  async function start() {
    if (!canStart || !icpn || siteId == null || !operation) return;
    // One confirmation starts at most one Batch, even on a double click.
    if (startedRef.current) return;
    startedRef.current = true;
    setBusy("start");
    setError(null);
    setRun(null);
    try {
      if (needsImage && file) {
        await runManagedBatch({
          alias, icpn, source: "image", operations: ["erase", "program", "verify"], file,
          siteIds: [siteId], retryLimit: 0, stopPolicy: { kind: "never" },
        }, {
          onBatch: next => { if (next.current_run) setRun(next.current_run); },
          onPollError: setError,
        });
      } else {
        const result = await runManagedRead(
          { alias, siteId, icpn, address: address ?? 0, length: length ?? 0 },
          { onRun: setRun, onPollError: setError });
        setRun(result.run);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Programming start failed");
    } finally {
      startedRef.current = false;
      setConfirmedKey(null);
      setBusy(null);
    }
  }

  async function acknowledge() {
    if (!run) return;
    setBusy("ack");
    try {
      setRun(await acknowledgeProgrammingRun(alias, run.run_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Acknowledge failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="ppuSiteCard" aria-label="Bundle Programming">
      <header className="ppuSiteCardHeader">
        <div>
          <small>PROGRAMMING</small>
          <h3>Bundle Programming</h3>
          <p data-testid="platform-programming-scope">
            Maintenance and diagnostic entry. Normal programming is EMode → Programming (Single PPU) and
            PMode → Factory Console; all three submit the same Manager Batch (here: one Site, one Cycle).
          </p>
          <p>
            Select IC, Site, Operation and its image or range. The Manager reuses the PPU&apos;s verified Programming
            Resources when they are identical (no B1/B2/B3, no FPGA load), otherwise activates the canonical Bundle
            before the Batch reserves them, then submits one Job with your Operation. No automatic retry.
          </p>
        </div>
      </header>

      {routesError && <p className="ppuRegistryMessage error" role="alert">{routesError}</p>}

      <div className="ppuRegistryAddForm">
        <label>
          <span>IC</span>
          <ICPickerField
            value={device}
            onChange={setDevice}
            levels={PICKER_LEVELS}
            disabled={Boolean(busy)}
          />
        </label>
        <label>
          <span>Operation</span>
          <select
            aria-label="Programming Operation"
            value={operation ?? ""}
            disabled={!operationOptions.length || Boolean(busy)}
            onChange={event => setChosenOperation(event.target.value)}
          >
            {operationOptions.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        {needsImage ? (
          <label>
            <span>Programming Image (.bin)</span>
            <input
              type="file"
              accept=".bin,application/octet-stream"
              aria-label="Image file"
              disabled={Boolean(busy)}
              onChange={event => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
        ) : operation != null && (
          <>
            <label>
              <span>Address</span>
              <input aria-label="Range address" value={rangeAddress} placeholder="0x08000000"
                disabled={Boolean(busy)} onChange={event => setRangeAddress(event.target.value)} />
            </label>
            <label>
              <span>Length (bytes)</span>
              <input aria-label="Range length" value={rangeLength} placeholder="1024"
                disabled={Boolean(busy)} onChange={event => setRangeLength(event.target.value)} />
            </label>
          </>
        )}
        <label>
          <span>Site</span>
          <select
            aria-label="Programming Site"
            value={siteId ?? ""}
            disabled={!siteOptions.length || Boolean(busy)}
            onChange={event => setChosenSite(Number(event.target.value))}
          >
            {siteOptions.map(site => <option key={site} value={site}>Site {site}</option>)}
          </select>
        </label>
        {icpn && routes && !siteOptions.length && (
          <p className="ppuRegistryMessage error" role="status">
            No Programming Route declares {icpn} on PPU {alias}.
          </p>
        )}
      </div>

      {error && <p className="ppuRegistryMessage error" role="alert">{error}</p>}

      <section aria-label="Programming start" className="ppuSiteCard">
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            disabled={!ready}
            onChange={event => setConfirmedKey(event.target.checked ? selectionKey : null)}
            aria-label="Confirm programming"
          />
          I confirm {operation ?? "—"} on {icpn ?? "—"} at {alias} Site {siteId ?? "—"} with this exact
          {needsImage ? " image" : " range"}.
        </label>
        <button className="ppuSiteButton primary" type="button" disabled={!canStart} onClick={() => void start()}>
          {busy === "start" ? "Running…" : "Start Programming"}
        </button>
      </section>

      {run && (
        <ProgrammingRunView run={run} onAcknowledge={() => void acknowledge()} acknowledging={busy === "ack"} />
      )}
    </section>
  );
}
