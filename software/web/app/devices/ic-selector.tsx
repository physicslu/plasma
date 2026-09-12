"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import {
  searchDevices,
  type DeviceSearchResult,
} from "../device-catalog-api";
import "./devices.css";

export type ICSelectorUsage = "lookup" | "picker";

export type ICSelectorProps = {
  usage?: ICSelectorUsage;
  apiBase: string;
  onSelect?: (device: DeviceSearchResult) => void;
};

function humanizeStatus(value: string | null): string {
  if (!value) return "—";
  return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function backendLabel(status: string): string {
  if (status === "mapped") return "OCD Mapped";
  if (status === "no_mapping") return "No OCD Mapping";
  if (status === "rejected") return "OCD Rejected";
  return humanizeStatus(status);
}

function statusClass(value: string | null): string {
  if (
    value === "mapped"
    || value === "engineering_verified"
    || value === "verified"
    || value === "passed"
    || value?.startsWith("verified_")
  ) return "verified";
  if (value === "rejected" || value === "failed" || value === "blocked") return "failed";
  return "pending";
}

function openOcdConfigLabel(status: string, zh: boolean): string {
  if (status === "mapped") return zh ? "OpenOCD 設定 · 已存在" : "OpenOCD config · Present";
  if (status === "no_mapping") return zh ? "OpenOCD 設定 · 未建立" : "OpenOCD config · Missing";
  if (status === "rejected") return zh ? "OpenOCD 設定 · 已拒絕" : "OpenOCD config · Rejected";
  return zh ? `OpenOCD 設定 · ${humanizeStatus(status)}` : `OpenOCD config · ${humanizeStatus(status)}`;
}

function manufacturerPartLabel(status: string | null, zh: boolean): string {
  if (status === "verified" || status === "engineering_verified" || status?.startsWith("verified_")) {
    return zh ? "原廠料號 · 已確認" : "Manufacturer part · Confirmed";
  }
  if (status === "rejected" || status === "failed" || status === "blocked") {
    return zh ? "原廠料號 · 未確認" : "Manufacturer part · Not confirmed";
  }
  return zh ? "原廠料號 · 待確認" : "Manufacturer part · Pending";
}

function physicalValidationLabel(kind: "PPU" | "Socket", status: string, zh: boolean): string {
  if (status === "no_evidence" || status === "not_verified") {
    return `${kind} · ${zh ? "未實機測試" : "Not hardware-tested"}`;
  }
  if (status === "engineering_verified" || status === "verified" || status === "passed") {
    return `${kind} · ${zh ? "實機測試通過" : "Hardware test passed"}`;
  }
  if (status === "rejected" || status === "failed" || status === "blocked") {
    return `${kind} · ${zh ? "實機測試未通過" : "Hardware test failed"}`;
  }
  return `${kind} · ${humanizeStatus(status)}`;
}

function physicalValidationDetail(status: string, zh: boolean): string {
  if (status === "no_evidence" || status === "not_verified") return zh ? "未實機測試" : "Not hardware-tested";
  if (status === "engineering_verified" || status === "verified" || status === "passed") return zh ? "實機測試通過" : "Hardware test passed";
  if (status === "rejected" || status === "failed" || status === "blocked") return zh ? "實機測試未通過" : "Hardware test failed";
  return humanizeStatus(status);
}

function shortRevision(value: string | null): string {
  return value ? value.slice(0, 12) : "—";
}

export function ICSelector({ usage = "lookup", apiBase, onSelect }: ICSelectorProps) {
  const { locale } = useI18n();
  const zh = locale === "zh-TW";
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DeviceSearchResult[]>([]);
  const [selected, setSelected] = useState<DeviceSearchResult | null>(null);
  const [catalogSize, setCatalogSize] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void searchDevices("", { apiBase, limit: 1, signal: controller.signal })
      .then(payload => setCatalogSize(payload.catalog_size))
      .catch(() => undefined);
    return () => controller.abort();
  }, [apiBase]);

  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) return;

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await searchDevices(normalized, {
          apiBase,
          limit: 30,
          signal: controller.signal,
        });
        setResults(payload.results);
        setCatalogSize(payload.catalog_size);
      } catch (searchError) {
        if (controller.signal.aborted) return;
        setResults([]);
        setError(searchError instanceof Error ? searchError.message : "Device search failed");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [apiBase, query]);

  function updateQuery(value: string) {
    setQuery(value);
    setResults([]);
    setError(null);
    setLoading(false);
    if (!value.trim()) setSelected(null);
  }

  function choose(device: DeviceSearchResult) {
    setSelected(device);
    onSelect?.(device);
  }

  return (
    <section className="icSelector" data-usage={usage}>
      <div className="icSelectorSearchPanel">
        <div className="icSelectorSearchHead">
          <div>
            <p className="icSelectorEyebrow">ICPN CATALOG · PRODUCTION ADMITTED</p>
            <h1>IC Selector</h1>
            <p>
              {zh
                ? "搜尋已通過 admission 的 exact commercial ICPN。可輸入 ICPN、Vendor、Family 或其組合。"
                : "Search admitted exact commercial ICPNs by ICPN, Vendor, Family, or a combination."}
            </p>
          </div>
          <div className="icSelectorCatalogMeta">
            <span>Admitted ICPNs</span>
            <b>{catalogSize?.toLocaleString() ?? "—"}</b>
            <small>{zh ? "Server production catalog" : "server production catalog"}</small>
          </div>
        </div>

        <label className="icSelectorSearchBox">
          <span>ICPN / Vendor / Family</span>
          <input
            autoComplete="off"
            autoFocus={usage === "lookup"}
            value={query}
            onChange={event => updateQuery(event.target.value)}
            placeholder="STM32F103C8T6 / STM32F4 / STMicroelectronics ..."
            aria-label="Search admitted ICPN"
          />
          <em>{loading ? (zh ? "搜尋中…" : "Searching…") : `${results.length} ${zh ? "筆結果" : "results"}`}</em>
        </label>

        {error && <div className="icSelectorError" role="alert">{error}</div>}

        {!query.trim() && (
          <div className="icSelectorEmpty">
            {zh
              ? "目前只列出已進入 production catalog 的 exact ICPN；research candidate 不會出現在這裡。"
              : "Only exact ICPNs admitted to the production catalog are listed; research candidates are excluded."}
          </div>
        )}

        {query.trim() && !loading && !error && results.length === 0 && (
          <div className="icSelectorEmpty">
            {zh ? "Production catalog 中找不到符合的 admitted ICPN。" : "No matching admitted ICPN exists in the production catalog."}
          </div>
        )}

        <div className="icSelectorResults" role="list">
          {results.map(device => {
            const active = selected?.vendor === device.vendor && selected?.identifier === device.identifier;
            return (
              <button
                type="button"
                className={`icSelectorResult ${active ? "selected" : ""}`}
                key={`${device.vendor}:${device.identifier}`}
                onClick={() => choose(device)}
                role="listitem"
              >
                <div className="icSelectorIdentity">
                  <strong>{device.icpn ?? device.identifier}</strong>
                  <span>Exact ICPN</span>
                </div>
                <div className="icSelectorTaxonomy">
                  <b>{device.vendor}</b>
                  <span>{device.family}</span>
                  {device.subfamily && <span>{device.subfamily}</span>}
                </div>
                <div className="icSelectorStatusStack">
                  <div className="icSelectorStatusRow icSelectorStatusPhysical">
                    <span className={statusClass(device.physical_validation.ppu_status)}>
                      {physicalValidationLabel("PPU", device.physical_validation.ppu_status, zh)}
                    </span>
                    <span className={statusClass(device.physical_validation.socket_status)}>
                      {physicalValidationLabel("Socket", device.physical_validation.socket_status, zh)}
                    </span>
                  </div>
                  <div className="icSelectorStatusRow icSelectorStatusEvidence">
                    <span className={statusClass(device.backend.mapping_status)}>
                      {openOcdConfigLabel(device.backend.mapping_status, zh)}
                    </span>
                    <span className={statusClass(device.catalog_verification.status)}>
                      {manufacturerPartLabel(device.catalog_verification.status, zh)}
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <aside className="icSelectorDetail" aria-live="polite">
        {selected ? (
          <>
            <p className="icSelectorEyebrow">SELECTED ADMITTED ICPN</p>
            <h2>{selected.icpn ?? selected.identifier}</h2>
            <span className="icSelectorKind">Exact ICPN · Catalog v{selected.catalog.version ?? "—"}</span>

            <dl>
              <div><dt>Vendor</dt><dd>{selected.vendor}</dd></div>
              <div><dt>Family</dt><dd>{selected.family}</dd></div>
              <div><dt>Series</dt><dd>{selected.subfamily ?? "—"}</dd></div>
              <div><dt>Base Device</dt><dd>{selected.base_device ?? "—"}</dd></div>
              <div><dt>Package</dt><dd>{selected.package ?? "—"}</dd></div>
              <div><dt>Pin Count</dt><dd>{selected.pin_count ?? "—"}</dd></div>
              <div><dt>Flash</dt><dd>{selected.flash_size ?? "—"}</dd></div>
              <div><dt>Temperature</dt><dd>{selected.temperature_grade ?? "—"}</dd></div>
              <div><dt>OpenOCD</dt><dd>{backendLabel(selected.backend.mapping_status)}</dd></div>
              <div><dt>Target CFG</dt><dd><code>{selected.backend.target_config}</code></dd></div>
              <div><dt>Mapping</dt><dd>{humanizeStatus(selected.backend.mapping_method)}</dd></div>
              <div><dt>Catalog Revision</dt><dd><code>{shortRevision(selected.catalog.revision_sha256)}</code></dd></div>
              <div><dt>Authority</dt><dd>{selected.catalog_verification.source_authority ?? "—"}</dd></div>
              <div><dt>ICPN Evidence</dt><dd>{humanizeStatus(selected.catalog_verification.status)}</dd></div>
              <div><dt>PPU</dt><dd>{physicalValidationDetail(selected.physical_validation.ppu_status, zh)}</dd></div>
              <div><dt>Socket</dt><dd>{physicalValidationDetail(selected.physical_validation.socket_status, zh)}</dd></div>
            </dl>

            <div className="icSelectorBoundary">
              {zh
                ? "原廠料號已確認且 OpenOCD 設定已存在，但這兩項都不代表 PPU 或 Socket 已完成實機測試。實機驗證必須另外建立對應的 PPU / Socket 測試證據。"
                : "The manufacturer part is confirmed and an OpenOCD configuration exists, but neither proves PPU or Socket hardware validation. PPU/Socket test evidence remains separate."}
            </div>
          </>
        ) : (
          <div className="icSelectorDetailEmpty">
            <b>{zh ? "尚未選擇 ICPN" : "No ICPN selected"}</b>
            <p>{zh ? "從 production catalog 搜尋結果選擇一筆以查看 admission 與 mapping 證據。" : "Choose a production-catalog result to inspect admission and mapping evidence."}</p>
          </div>
        )}
      </aside>
    </section>
  );
}
