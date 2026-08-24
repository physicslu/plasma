"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  configuredDeviceApiBase,
  searchDevices,
  type DeviceSearchResult,
} from "../device-catalog-api";
import "./devices.css";

export type ICSelectorUsage = "lookup" | "picker";

export type ICSelectorProps = {
  usage?: ICSelectorUsage;
  apiBase?: string;
  onSelect?: (device: DeviceSearchResult) => void;
};

function humanizeStatus(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

function identifierKindLabel(kind: string): string {
  if (kind === "manufacturer_part_number") return "Exact ICPN";
  if (kind === "cmsis_device_name") return "Device Name";
  if (kind === "ordering_pattern") return "Ordering Pattern";
  if (kind === "family_alias") return "Family Alias";
  return humanizeStatus(kind);
}

function backendLabel(status: string): string {
  if (status === "mapped") return "OCD Mapped";
  if (status === "mapping_candidate") return "OCD Candidate";
  if (status === "no_mapping") return "No OCD Mapping";
  if (status === "rejected") return "OCD Rejected";
  return humanizeStatus(status);
}

function statusClass(value: string): string {
  if (value === "mapped" || value === "engineering_verified" || value === "verified") return "verified";
  if (value === "rejected" || value === "failed" || value === "blocked") return "failed";
  return "pending";
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

  const resolvedApiBase = useMemo(() => apiBase ?? configuredDeviceApiBase(), [apiBase]);

  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) return;

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await searchDevices(normalized, {
          apiBase: resolvedApiBase,
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
  }, [query, resolvedApiBase]);

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
            <p className="icSelectorEyebrow">DEVICE CATALOG · READ ONLY</p>
            <h1>IC Selector</h1>
            <p>
              {zh
                ? "直接輸入 ICPN／IC identifier。Exact match 優先，其次 Prefix、Partial match。"
                : "Type an ICPN or IC identifier directly. Exact matches rank before prefix and partial matches."}
            </p>
          </div>
          <div className="icSelectorCatalogMeta">
            <span>Catalog</span>
            <b>{catalogSize?.toLocaleString() ?? "—"}</b>
            <small>{zh ? "Server 回報的 canonical identifiers" : "canonical identifiers reported by the server"}</small>
          </div>
        </div>

        <label className="icSelectorSearchBox">
          <span>ICPN / Identifier</span>
          <input
            autoComplete="off"
            autoFocus={usage === "lookup"}
            value={query}
            onChange={event => updateQuery(event.target.value)}
            placeholder="STM32F103C8T6 / LPC845 / nRF52840 ..."
            aria-label="Search ICPN or IC identifier"
          />
          <em>{loading ? (zh ? "搜尋中…" : "Searching…") : `${results.length} ${zh ? "筆結果" : "results"}`}</em>
        </label>

        {error && <div className="icSelectorError" role="alert">{error}</div>}

        {!query.trim() && (
          <div className="icSelectorEmpty">
            {zh
              ? "輸入料號即可查詢；不需要先選 Vendor 或 Family。"
              : "Start with the part identifier; Vendor and Family selection is not required."}
          </div>
        )}

        {query.trim() && !loading && !error && results.length === 0 && (
          <div className="icSelectorEmpty">
            {zh ? "找不到符合的 IC identifier。" : "No matching IC identifier was found."}
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
                  <span>{identifierKindLabel(device.identifier_kind)}</span>
                </div>
                <div className="icSelectorTaxonomy">
                  <b>{device.vendor}</b>
                  <span>{device.family}</span>
                  {device.subfamily && <span>{device.subfamily}</span>}
                </div>
                <div className="icSelectorStatusRow">
                  <span className={statusClass(device.backend.mapping_status)}>{backendLabel(device.backend.mapping_status)}</span>
                  <span className="pending">PPU · {zh ? "無實體證據" : "No evidence"}</span>
                  <span className="pending">Socket · {zh ? "無實體證據" : "No evidence"}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <aside className="icSelectorDetail" aria-live="polite">
        {selected ? (
          <>
            <p className="icSelectorEyebrow">SELECTED DEVICE</p>
            <h2>{selected.icpn ?? selected.identifier}</h2>
            <span className="icSelectorKind">{identifierKindLabel(selected.identifier_kind)}</span>

            <dl>
              <div><dt>Vendor</dt><dd>{selected.vendor}</dd></div>
              <div><dt>Family</dt><dd>{selected.family}</dd></div>
              <div><dt>Subfamily</dt><dd>{selected.subfamily ?? "—"}</dd></div>
              <div><dt>Plasma Series</dt><dd>{selected.plasma_series || "—"}</dd></div>
              <div><dt>Package</dt><dd>{selected.package ?? (zh ? "目前資料未提供" : "Not in current catalog")}</dd></div>
              <div><dt>CPU</dt><dd>{selected.cpu_architectures.join(", ") || "—"}</dd></div>
              <div><dt>OpenOCD</dt><dd>{backendLabel(selected.backend.mapping_status)}</dd></div>
              <div><dt>Target CFG</dt><dd><code>{selected.backend.target_config}</code></dd></div>
              <div><dt>PPU</dt><dd>{zh ? "尚無實體驗證證據" : "No physical validation evidence"}</dd></div>
              <div><dt>Socket</dt><dd>{zh ? "尚無實體驗證證據" : "No physical validation evidence"}</dd></div>
            </dl>

            <div className="icSelectorBoundary">
              {zh
                ? "OpenOCD mapping 不等於 PPU 或 Socket 驗證。實體支援必須由特定 Programming Configuration 的證據建立。"
                : "An OpenOCD mapping is not PPU or Socket verification. Physical support requires evidence for a specific Programming Configuration."}
            </div>
          </>
        ) : (
          <div className="icSelectorDetailEmpty">
            <b>{zh ? "尚未選擇 IC" : "No IC selected"}</b>
            <p>{zh ? "從搜尋結果選擇一筆以查看完整資料。" : "Choose a search result to inspect its catalog details."}</p>
          </div>
        )}
      </aside>
    </section>
  );
}
