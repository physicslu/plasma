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

type OpenOcdTagState = "mapped" | "candidate" | "no_mapping";

/** Display projection only: source candidates never change Production routing. */
function openOcdTagState(device: DeviceSearchResult): OpenOcdTagState {
  if (device.backend.mapping_status === "mapped") return "mapped";
  if (
    device.backend.mapping_status === "no_mapping"
    && !device.backend.target_config
    && device.catalog.scope === "production_admitted"
    && device.backend_candidate?.status === "research_only"
    && device.backend_candidate.production_mapping_status === "no_mapping"
    && device.backend_candidate.executable === false
    && device.backend_candidate.production_binding_authorized === false
    && device.backend_candidate.hardware_runtime_ready === false
    && device.backend_candidate.family === device.family
  ) return "candidate";
  return "no_mapping";
}

function openOcdConfigLabel(status: OpenOcdTagState, zh: boolean): string {
  if (status === "mapped") return zh ? "OpenOCD 設定 · 已存在" : "OpenOCD config · Present";
  if (status === "candidate") return zh ? "OpenOCD 設定 · 候選" : "OpenOCD config · Candidate";
  return zh ? "OpenOCD 設定 · 未建立" : "OpenOCD config · Missing";
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

function voltageRange(value?: { min: number; max: number }): string {
  if (!value) return "—";
  return `${value.min}–${value.max} V`;
}

function formatClock(
  value: { manufacturer_min: number | null; manufacturer_max: number | null; manufacturer_recommended: number | null; status: string },
  zh: boolean,
): string {
  if (
    value.manufacturer_min === null
    && value.manufacturer_max === null
    && value.manufacturer_recommended === null
  ) {
    return zh ? "原廠文件未明確指定" : "Not specified by manufacturer";
  }
  const parts = [];
  if (value.manufacturer_min !== null) parts.push(`min ${value.manufacturer_min.toLocaleString()} Hz`);
  if (value.manufacturer_max !== null) parts.push(`max ${value.manufacturer_max.toLocaleString()} Hz`);
  if (value.manufacturer_recommended !== null) parts.push(`recommended ${value.manufacturer_recommended.toLocaleString()} Hz`);
  return parts.join(" · ");
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
                    <span className={openOcdTagState(device) === "mapped" ? "verified" : openOcdTagState(device) === "candidate" ? "pending" : "unmapped"}>
                      {openOcdConfigLabel(openOcdTagState(device), zh)}
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

            <section className="icSelectorProfileSection" data-profile-section="device">
              <div className="icSelectorProfileHead">
                <span>01</span>
                <div>
                  <h3>{zh ? "IC Information" : "IC Information"}</h3>
                  <p>{zh ? "IC 身分、工作電氣特性與 Memory Map" : "Identity, operating electrical characteristics, and memory map"}</p>
                </div>
              </div>
              <dl>
                <div><dt>Vendor</dt><dd>{selected.vendor}</dd></div>
                <div><dt>Family</dt><dd>{selected.family}</dd></div>
                <div><dt>Series</dt><dd>{selected.subfamily ?? "—"}</dd></div>
                <div><dt>Base Device</dt><dd>{selected.base_device ?? "—"}</dd></div>
                <div><dt>Package</dt><dd>{selected.package ?? "—"}</dd></div>
                <div><dt>Pin Count</dt><dd>{selected.pin_count ?? "—"}</dd></div>
                <div><dt>Flash</dt><dd>{selected.flash_size ?? "—"}</dd></div>
                {selected.selected_profile ? (
                  <>
                    <div><dt>SRAM</dt><dd>{selected.selected_profile.device.memory_map.sram ? `${selected.selected_profile.device.memory_map.sram.size_bytes / 1024} KiB` : "—"}</dd></div>
                    <div><dt>{zh ? "工作 VDD" : "Operating VDD"}</dt><dd>{voltageRange(selected.selected_profile.device.operating_electrical.vdd_v)}</dd></div>
                    <div><dt>Main Flash Map</dt><dd><code>{selected.selected_profile.device.memory_map.main_flash.start}–{selected.selected_profile.device.memory_map.main_flash.end}</code></dd></div>
                    <div><dt>{zh ? "Flash Page" : "Flash page"}</dt><dd>{selected.selected_profile.device.memory_map.main_flash.page_size_bytes} bytes × {selected.selected_profile.device.memory_map.main_flash.page_count}</dd></div>
                  </>
                ) : (
                  <div><dt>{zh ? "Device Profile" : "Device profile"}</dt><dd>{zh ? "尚未建立 manufacturer enrichment" : "Manufacturer enrichment not available"}</dd></div>
                )}
              </dl>
            </section>

            <section className="icSelectorProfileSection" data-profile-section="programming">
              <div className="icSelectorProfileHead">
                <span>02</span>
                <div>
                  <h3>{zh ? "Programming" : "Programming"}</h3>
                  <p>{zh ? "燒錄介面、電氣條件、Flash geometry 與程序" : "Interface, electrical conditions, Flash geometry, and programming flow"}</p>
                </div>
              </div>
              {selected.selected_profile ? (
                <dl>
                  <div><dt>{zh ? "燒錄 VDD" : "Programming VDD"}</dt><dd>{voltageRange(selected.selected_profile.programming.electrical.vdd_programming_v)}</dd></div>
                  <div><dt>External VPP</dt><dd>{selected.selected_profile.programming.electrical.external_vpp?.required ? (zh ? "需要" : "Required") : (zh ? "不需要" : "Not required")}</dd></div>
                  {Object.entries(selected.selected_profile.programming.interfaces).map(([name, iface]) => (
                    <div key={name}>
                      <dt>{name}</dt>
                      <dd>
                        <strong>{formatClock(iface.clock_hz, zh)}</strong>
                        {iface.required_signal_pins?.length ? (
                          <div>{zh ? "Pins" : "Pins"}: {iface.required_signal_pins.map(pin => `${pin.signal}(${pin.mcu_pin})`).join(", ")}</div>
                        ) : null}
                      </dd>
                    </div>
                  ))}
                  <div><dt>{zh ? "Erase 單位" : "Erase unit"}</dt><dd>{selected.selected_profile.programming.flash_geometry.erase_unit_bytes} bytes</dd></div>
                  <div><dt>{zh ? "Program 單位" : "Program unit"}</dt><dd>{selected.selected_profile.programming.flash_geometry.program_unit} · {selected.selected_profile.programming.flash_geometry.program_unit_bytes} bytes</dd></div>
                  <div><dt>{zh ? "燒錄程序" : "Programming flow"}</dt><dd className="icSelectorProgramFlow">{selected.selected_profile.programming.program_model.normal_write_flow.join(" → ")}</dd></div>
                  <div><dt>OpenOCD</dt><dd>{backendLabel(selected.backend.mapping_status)} · <code>{selected.backend.target_config}</code></dd></div>
                </dl>
              ) : (
                <div className="icSelectorProfileUnavailable">
                  {zh ? "此 ICPN 尚未建立 manufacturer-derived Programming Profile。" : "No manufacturer-derived Programming Profile exists for this ICPN yet."}
                </div>
              )}
            </section>

            <section className="icSelectorProfileSection" data-profile-section="compatibility">
              <div className="icSelectorProfileHead">
                <span>03</span>
                <div>
                  <h3>{zh ? "PLASMA Compatibility" : "PLASMA Compatibility"}</h3>
                  <p>{zh ? "Site / Socket / 實機資格是獨立證據，不由 Catalog 或 OpenOCD 推論" : "Site, socket, and physical qualification remain independent evidence"}</p>
                </div>
              </div>
              <dl>
                <div><dt>PPU</dt><dd>{physicalValidationDetail(selected.physical_validation.ppu_status, zh)}</dd></div>
                <div><dt>Socket</dt><dd>{physicalValidationDetail(selected.physical_validation.socket_status, zh)}</dd></div>
                <div><dt>{zh ? "Site 電氣相容" : "Site electrical"}</dt><dd>{selected.selected_profile ? humanizeStatus(selected.selected_profile.plasma_compatibility.site_electrical_compatibility) : (zh ? "未評估" : "Not evaluated")}</dd></div>
                <div><dt>Hardware Ready</dt><dd>{selected.selected_profile?.plasma_compatibility.hardware_runtime_ready ? "TRUE" : "FALSE"}</dd></div>
                <div><dt>{zh ? "實體燒錄資格" : "Physical programming"}</dt><dd>{selected.selected_profile?.plasma_compatibility.physical_programming_qualified ? "QUALIFIED" : "NOT QUALIFIED"}</dd></div>
              </dl>
            </section>

            <details className="icSelectorEvidenceDetails">
              <summary>{zh ? "Advanced Backend / Evidence" : "Advanced Backend / Evidence"}</summary>
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
              {!selected.backend_providers?.length && selected.backend_source_reference && (
                <>
                  <div><dt>{zh ? "Backend Provider" : "Backend provider"}</dt><dd>{selected.backend_source_reference.provider_name} ({selected.backend_source_reference.provider_id})</dd></div>
                  <div><dt>{zh ? "來源版本" : "Source version"}</dt><dd>{selected.backend_source_reference.source_version ?? (zh ? "未確認" : "Not attested")}</dd></div>
                  <div><dt>{zh ? "來源 Commit" : "Source commit"}</dt><dd><code>{selected.backend_source_reference.source_commit ?? (zh ? "未確認" : "Not attested")}</code></dd></div>
                  <div><dt>{zh ? "來源儲存庫" : "Source repository"}</dt><dd><code>{selected.backend_source_reference.source_repository ?? "—"}</code></dd></div>
                  <div><dt>{zh ? "發行 Runtime ID" : "Pinned release runtime ID"}</dt><dd><code>{selected.backend_source_reference.pinned_release_runtime_id ?? (zh ? "未確認" : "Not attested")}</code></dd></div>
                  <div><dt>{zh ? "已安裝 Runtime ID" : "Installed runtime ID"}</dt><dd>{selected.backend_source_reference.installed_runtime_id ?? (zh ? "未提供實機證據" : "No device attestation")}</dd></div>
                  <div><dt>Binary SHA-256</dt><dd><code>{selected.backend_source_reference.installed_binary_sha256 ?? (zh ? "未提供實機證據" : "No device attestation")}</code></dd></div>
                  <div><dt>{zh ? "驗證範圍" : "Evidence scope"}</dt><dd>{selected.backend_source_reference.evidence_scope === "catalog_mapping_only"
                    ? (zh ? "僅 Catalog 路由證據" : "Catalog route evidence only")
                    : (zh ? "僅固定來源研究證據" : "Pinned source research only")}</dd></div>
                </>
              )}

              {selected.backend_providers?.map((provider, idx) => (
                <div key={provider.provider_id} className="icSelectorBackendProvider">
                  <dt>{zh ? "Backend 選項" : "Backend option"} {idx + 1}</dt>
                  <dd>
                    <strong>{provider.provider_distribution} · {provider.mapping_status === "candidate" ? "Candidate" : "Mapped"}</strong>
                    <div>{zh ? "來源版本" : "Source version"}: {provider.source_version ?? (zh ? "未確認" : "Unknown")}</div>
                    <div>Source Repository: <code>{provider.source_repository}</code></div>
                    <div>Source Commit: <code>{provider.source_commit}</code></div>
                    <div>Runtime ID: <code>{provider.declared_release_runtime_id ?? (zh ? "未建立正式發行綁定" : "No declared release binding")}</code></div>
                    <div>Flash Driver: <code>{provider.flash_driver ?? (zh ? "未個別驗證" : "Not individually proven")}</code></div>
                    <div>Target CFG: <code>{provider.target_config}</code></div>
                    <div>{zh ? "已安裝 Runtime" : "Installed runtime"}: {provider.installed_runtime_id ?? (zh ? "尚無實機安裝證據" : "Not attested")}</div>
                    <div>Installed Binary SHA-256: <code>{provider.installed_binary_sha256 ?? (zh ? "尚無實機安裝證據" : "Not attested")}</code></div>
                    <div>{zh ? "Provider 層級離線建置證據（非逐顆 MCU 驗證）" : "Provider-level offline build evidence (not per-IC qualification)"}: {provider.software_build_evidence.length === 0
                      ? (zh ? "無此版本的獨立建置驗證紀錄" : "No independent build evidence for this variant")
                      : provider.software_build_evidence.map(build => (
                        <div key={build.architecture} className="icSelectorBackendBuild">
                          <a href={`https://github.com/physicslu/plasma/actions/runs/${build.github_actions_run_id}`} target="_blank" rel="noreferrer">
                            {build.architecture} · {build.qualification}
                          </a>
                          <div>Build Runtime ID: <code>{build.runtime_id}</code></div>
                          <div>Artifact SHA-256: <code>{build.artifact_sha256}</code></div>
                          <div>Payload SHA-256: <code>{build.payload_sha256}</code></div>
                          <div>{zh ? "驗證界線" : "Evidence scope"}: {build.scope} · {zh ? "未實機測試" : "No physical test"}</div>
                        </div>
                      ))}
                    </div>
                    <div>{zh ? "執行權限" : "Execution"}: {zh ? "未開放（僅 Metadata）" : "Not enabled (metadata only)"}</div>
                  </dd>
                </div>
              ))}
              {selected.backend_candidate && (
                <>
                  <div><dt>{zh ? "候選引擎" : "Candidate engine"}</dt><dd>{selected.backend_candidate.flash_driver} · {zh ? "僅研究" : "research only"}</dd></div>
                  <div><dt>{zh ? "預期晶片 ID" : "Expected device ID"}</dt><dd><code>{selected.backend_candidate.expected_device_id}</code> ({zh ? "原始碼推定，未實測" : "source inferred, not measured"})</dd></div>
                  <div><dt>{zh ? "候選設定檔" : "Candidate config"}</dt><dd><code>{selected.backend_candidate.target_config_source_path}</code> ({zh ? "未安裝" : "not installed"})</dd></div>
                  <div><dt>{zh ? "來源 Commit" : "Source commit"}</dt><dd><code>{shortRevision(selected.backend_candidate.source_commit)}</code></dd></div>
                  {selected.backend_candidate.loader_source_path && (
                    <div><dt>{zh ? "候選 Flash Loader" : "Candidate Flash loader"}</dt><dd><code>{selected.backend_candidate.loader_source_path}</code> ({zh ? "未安裝／未驗證" : "not installed/verified"})</dd></div>
                  )}
                  {selected.backend_candidate.dfp_exact_variant_status && (
                    <div><dt>{zh ? "DFP 精確料號" : "DFP exact variant"}</dt><dd>{selected.backend_candidate.dfp_exact_variant_status === "exact" ? (zh ? "符合舊版 DFP" : "matched in pinned DFP") : (zh ? "僅 Base Device，待補強適用性" : "base device only; applicability pending")}</dd></div>
                  )}
                </>
              )}
              <div><dt>Catalog Revision</dt><dd><code>{shortRevision(selected.catalog.revision_sha256)}</code></dd></div>
              <div><dt>Authority</dt><dd>{selected.catalog_verification.source_authority ?? "—"}</dd></div>
              <div><dt>ICPN Evidence</dt><dd>{humanizeStatus(selected.catalog_verification.status)}</dd></div>
              <div><dt>PPU</dt><dd>{physicalValidationDetail(selected.physical_validation.ppu_status, zh)}</dd></div>
              <div><dt>Socket</dt><dd>{physicalValidationDetail(selected.physical_validation.socket_status, zh)}</dd></div>
              {selected.selected_profile && (
                <>
                  <div><dt>{zh ? "Manufacturer Baseline" : "Manufacturer baseline"}</dt><dd><code>{selected.selected_profile.manufacturer_baseline.baseline_id}</code></dd></div>
                  <div><dt>Baseline SHA-256</dt><dd><code>{selected.selected_profile.manufacturer_baseline.sha256}</code></dd></div>
                </>
              )}
            </dl>
            </details>

            {selected.backend_candidate && (
              <div className="icSelectorCandidateBoundary" role="note">
                <strong>{zh ? "Backend Candidate Registry · 尚不可燒錄" : "Backend Candidate Registry · Not programmable"}</strong>
                <p>{zh
                  ? "僅有固定來源版本的研究證據；預期 Device ID 尚未從實體 IC 讀取，FPGA SWD、電氣條件及 Flash 操作都尚未驗證。候選資訊不會修改 Production Mapping。"
                  : "Source-pinned research only. Silicon ID, FPGA SWD, electrical limits and Flash operations have not been verified. This candidate does not modify Production Mapping."}</p>
              </div>
            )}
            <div className="icSelectorBoundary">
              {selected.backend_candidate
                ? (zh
                  ? "這顆 IC 已收錄於 Production Catalog，但目前沒有可執行的 OpenOCD Backend，無法視為已支援燒錄。"
                  : "This IC is in the Production Catalog, but no executable OpenOCD backend is mapped. It is not programming-qualified.")
                : (selected.backend.mapping_status === "mapped"
                  ? (zh
                    ? "原廠料號已確認且 OpenOCD 設定已存在，但這兩項都不代表 PPU 或 Socket 已完成實機測試。實機驗證必須另外建立對應的 PPU / Socket 測試證據。"
                    : "The manufacturer part is confirmed and an OpenOCD configuration exists, but neither proves PPU or Socket hardware validation. PPU/Socket test evidence remains separate.")
                  : (zh
                    ? "這顆原廠料號已收錄，但尚無正式 OpenOCD Mapping 或足夠實機證據。"
                    : "This manufacturer part is cataloged without a Production OpenOCD mapping or physical qualification."))}
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
