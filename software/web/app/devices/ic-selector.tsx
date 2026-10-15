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

function softwareQualificationClass(state: string | undefined): string {
  if (state === "SUPPORTED") return "verified";
  if (state === "UNSUPPORTED") return "failed";
  if (state === "CANDIDATE") return "pending";
  return "unmapped";
}

function softwareQualificationLabel(state: string | undefined, zh: boolean): string {
  if (!state) return zh ? "軟體資格 · 未提供" : "Software · Unavailable";
  return zh ? `軟體資格 · ${state}` : `Software · ${state}`;
}

function formatFlashBytes(value: number): string {
  if (value % (1024 * 1024) === 0) return `${value / (1024 * 1024)} MiB`;
  if (value % 1024 === 0) return `${value / 1024} KiB`;
  return `${value} bytes`;
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
  value: { manufacturer_min: number | null; manufacturer_max: number | null; manufacturer_recommended: number | null; status: string } | undefined,
  zh: boolean,
): string {
  if (!value) return zh ? "此介面未定義 Debug Clock" : "No debug clock defined for this interface";
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

const SEARCH_PAGE_SIZE = 30;

export function ICSelector({ usage = "lookup", apiBase, onSelect }: ICSelectorProps) {
  const { locale } = useI18n();
  const zh = locale === "zh-TW";
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DeviceSearchResult[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pageOffset, setPageOffset] = useState(0);
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
          limit: SEARCH_PAGE_SIZE,
          offset: pageOffset,
          signal: controller.signal,
        });
        setResults(payload.results);
        setTotalCount(payload.total_count);
        setCatalogSize(payload.catalog_size);
      } catch (searchError) {
        if (controller.signal.aborted) return;
        setResults([]);
        setTotalCount(0);
        setError(searchError instanceof Error ? searchError.message : "Device search failed");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 180);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [apiBase, pageOffset, query]);

  function updateQuery(value: string) {
    setQuery(value);
    setResults([]);
    setTotalCount(0);
    setPageOffset(0);
    setSelected(null);
    setError(null);
    setLoading(false);
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
          <em>
            {loading
              ? (zh ? "搜尋中…" : "Searching…")
              : (zh
                  ? (totalCount > 0
                      ? `顯示 ${(pageOffset + 1).toLocaleString()}–${(pageOffset + results.length).toLocaleString()} / 共 ${totalCount.toLocaleString()} 筆`
                      : "顯示 0 / 共 0 筆")
                  : (totalCount > 0
                      ? `Showing ${(pageOffset + 1).toLocaleString()}–${(pageOffset + results.length).toLocaleString()} / ${totalCount.toLocaleString()}`
                      : "Showing 0 / 0"))}
          </em>
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
                    <span className={softwareQualificationClass(device.openocd_software_qualification?.software_state)}>
                      {softwareQualificationLabel(device.openocd_software_qualification?.software_state, zh)}
                    </span>
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

        {totalCount > SEARCH_PAGE_SIZE && (
          <nav className="icSelectorPagination" aria-label={zh ? "ICPN 搜尋分頁" : "ICPN search pagination"}>
            <button
              type="button"
              disabled={loading || pageOffset === 0}
              onClick={() => {
                setSelected(null);
                setPageOffset(Math.max(0, pageOffset - SEARCH_PAGE_SIZE));
              }}
            >
              {zh ? "← 上一頁" : "← Previous"}
            </button>
            <span>
              {zh
                ? `第 ${Math.floor(pageOffset / SEARCH_PAGE_SIZE) + 1} / ${Math.ceil(totalCount / SEARCH_PAGE_SIZE)} 頁`
                : `Page ${Math.floor(pageOffset / SEARCH_PAGE_SIZE) + 1} / ${Math.ceil(totalCount / SEARCH_PAGE_SIZE)}`}
            </span>
            <button
              type="button"
              disabled={loading || pageOffset + results.length >= totalCount}
              onClick={() => {
                setSelected(null);
                setPageOffset(pageOffset + SEARCH_PAGE_SIZE);
              }}
            >
              {zh ? "下一頁 →" : "Next →"}
            </button>
          </nav>
        )}
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
                  <p>
                    {selected.manufacturer_device_basic_profile
                      ? (zh ? "ST 官方 Product Selector / eStore 基本規格" : "Basic specifications from official ST Product Selector / eStore")
                      : selected.nxp_manufacturer_device_profile
                        ? (zh ? "NXP 官方單料號規格；未知欄位不推估，不代表燒錄資格" : "NXP exact-part evidence; unknown fields are not inferred or programming-qualified")
                        : selected.microchip_phase1_ic_information
                          ? (zh ? "Microchip 原廠 MCP 精確料號 + DS60001513G 訂購規則；Phase 1 IDENTIFIED，Phase 2 尚未驗證" : "Microchip official MCP exact part + DS60001513G ordering evidence; Phase 1 IDENTIFIED, Phase 2 unqualified")
                          : (zh ? "基本身分來自 Catalog；Manufacturer Device Basic Profile 尚未建立" : "Catalog identity only; Manufacturer Device Basic Profile is not available")}
                  </p>
                </div>
              </div>
              <dl>
                <div><dt>ICPN</dt><dd>{selected.icpn ?? selected.identifier}</dd></div>
                <div><dt>Base Device</dt><dd>{selected.base_device ?? "—"}{selected.nxp_manufacturer_device_profile ? (zh ? "（單料號暫代，未驗證共用 Base）" : " (exact SKU placeholder; common base unverified)") : ""}</dd></div>
                <div><dt>Package</dt><dd>{selected.package ?? "—"}</dd></div>
                <div><dt>Pin Count</dt><dd>{selected.pin_count ?? "—"}</dd></div>
                <div><dt>Flash</dt><dd>{selected.flash_size ?? "—"}</dd></div>
                <div><dt>RAM</dt><dd>{selected.manufacturer_device_basic_profile?.ram_size ?? selected.nxp_manufacturer_device_profile?.ram_size ?? selected.microchip_phase1_ic_information?.ram_size ?? "—"}</dd></div>
                <div>
                  <dt>{zh ? "工作 VDD" : "Operating VDD"}</dt>
                  <dd>{selected.manufacturer_device_basic_profile
                    ? voltageRange(selected.manufacturer_device_basic_profile.operating_vdd_v)
                    : selected.microchip_phase1_ic_information
                        ? (zh ? "PARTIAL（家族資料，未確認料號工作電壓）" : "PARTIAL (family only; exact working voltage unknown)")
                        : voltageRange(selected.nxp_manufacturer_device_profile?.operating_vdd_v ?? undefined)}</dd>
                </div>
                <div>
                  <dt>I/O Supply</dt>
                  <dd>{selected.manufacturer_device_basic_profile?.io_supply_v
                    ? voltageRange(selected.manufacturer_device_basic_profile.io_supply_v)
                    : selected.nxp_manufacturer_device_profile
                      ? (zh ? "未有個別原廠證據" : "Not independently sourced")
                      : selected.microchip_phase1_ic_information
                        ? (zh ? "UNKNOWN（無獨立原廠證據）" : "UNKNOWN (no independent manufacturer evidence)")
                        : "—"}</dd>
                </div>
                <div>
                  <dt>VDDA</dt>
                  <dd>{selected.manufacturer_device_basic_profile?.vdda_v
                    ? voltageRange(selected.manufacturer_device_basic_profile.vdda_v)
                    : selected.nxp_manufacturer_device_profile
                      ? (zh ? "未有個別原廠證據" : "Not independently sourced")
                      : selected.microchip_phase1_ic_information
                        ? (zh ? "UNKNOWN（無獨立原廠證據）" : "UNKNOWN (no independent manufacturer evidence)")
                        : "—"}</dd>
                </div>
                <div>
                  <dt>{zh ? "工作溫度" : "Operating Temperature"}</dt>
                  <dd>{selected.manufacturer_device_basic_profile
                    ? `${selected.manufacturer_device_basic_profile.operating_temperature_c.min}–${selected.manufacturer_device_basic_profile.operating_temperature_c.max} °C`
                    : selected.nxp_manufacturer_device_profile
                      ? `${selected.nxp_manufacturer_device_profile.operating_temperature_c.min}–${selected.nxp_manufacturer_device_profile.operating_temperature_c.max} °C`
                      : (selected.temperature_grade ?? "—")}</dd>
                </div>
                {selected.microchip_phase1_ic_information && (
                  <>
                    <div><dt>Core Model</dt><dd>{selected.microchip_phase1_ic_information.core_model}</dd></div>
                    <div><dt>Phase 1 Evidence</dt><dd>IDENTIFIED · S1_complete: NO · DS60001513G p.14 / p.16</dd></div>
                  </>
                )}
              </dl>
            </section>

            <section className="icSelectorProfileSection" data-profile-section="programming">
              <div className="icSelectorProfileHead">
                <span>02</span>
                <div>
                  <h3>{zh ? "Programming" : "Programming"}</h3>
                  <p>{zh ? "Phase 2 軟體資格、燒錄介面、電氣條件、Flash geometry 與程序" : "Phase 2 software qualification, interfaces, electrical conditions, Flash geometry, and flow"}</p>
                </div>
              </div>

              {selected.openocd_software_qualification ? (
                <>
                  <dl>
                    <div>
                      <dt>{zh ? "Software Qualification" : "Software Qualification"}</dt>
                      <dd><strong>{selected.openocd_software_qualification.software_state}</strong>{selected.openocd_software_qualification.reviewed ? (zh ? " · exact ICPN 已審查" : " · exact ICPN reviewed") : (zh ? " · exact ICPN 尚未完成 Phase 2 審查" : " · exact ICPN not yet Phase 2 reviewed")}</dd>
                    </div>
                    {selected.openocd_software_qualification.provider && (
                      <>
                        <div><dt>{zh ? "Provider" : "Provider"}</dt><dd>OpenOCD {selected.openocd_software_qualification.provider.version}</dd></div>
                        <div><dt>Target CFG</dt><dd><code>{selected.openocd_software_qualification.provider.target_config}</code></dd></div>
                        <div><dt>Flash Driver</dt><dd><code>{selected.openocd_software_qualification.provider.flash_driver}</code></dd></div>
                      </>
                    )}
                    {selected.openocd_software_qualification.programming && (
                      <>
                        <div><dt>{zh ? "Programming Profile" : "Programming Profile"}</dt><dd><code>{selected.openocd_software_qualification.programming.programming_profile_id}</code></dd></div>
                        <div><dt>{zh ? "燒錄 VDD" : "Programming VDD"}</dt><dd>{voltageRange(selected.openocd_software_qualification.programming.electrical.vdd_programming_v)}</dd></div>
                        <div><dt>External VPP</dt><dd>{selected.openocd_software_qualification.programming.electrical.external_vpp_required ? (zh ? "需要" : "Required") : (zh ? "不需要" : "Not required")}</dd></div>
                        <div><dt>{zh ? "介面" : "Transports"}</dt><dd>{selected.openocd_software_qualification.programming.debug_transport.join(" · ")}</dd></div>
                        <div><dt>{zh ? "Flash 容量" : "Flash size"}</dt><dd>{formatFlashBytes(selected.openocd_software_qualification.programming.flash_geometry.main_flash_size_bytes)}</dd></div>
                        <div><dt>{zh ? "Erase 單位" : "Erase unit"}</dt><dd>{selected.openocd_software_qualification.programming.flash_geometry.erase_unit_bytes} bytes</dd></div>
                        <div><dt>{zh ? "Program 單位" : "Program unit"}</dt><dd>{selected.openocd_software_qualification.programming.flash_geometry.program_unit} · {selected.openocd_software_qualification.programming.flash_geometry.program_unit_bytes} bytes</dd></div>
                        <div><dt>{zh ? "Page Count" : "Page count"}</dt><dd>{selected.openocd_software_qualification.programming.flash_geometry.page_count}</dd></div>
                      </>
                    )}
                    {Object.keys(selected.openocd_software_qualification.operations).length > 0 && (
                      <div>
                        <dt>{zh ? "Qualified Operations" : "Qualified Operations"}</dt>
                        <dd>{Object.entries(selected.openocd_software_qualification.operations).map(([name, op]) => `${name.toUpperCase()}=${op.state}`).join(" · ")}</dd>
                      </div>
                    )}
                    <div><dt>{zh ? "CFG Mapping" : "CFG Mapping"}</dt><dd>{backendLabel(selected.backend.mapping_status)} · <code>{selected.backend.target_config}</code></dd></div>

                    {selected.selected_profile && Object.entries(selected.selected_profile.programming.interfaces).map(([name, iface]) => (
                      <div key={name}>
                        <dt>{name} {zh ? "原廠細節" : "manufacturer detail"}</dt>
                        <dd>
                          <strong>{iface.clock_hz ? formatClock(iface.clock_hz, zh) : humanizeStatus(iface.status ?? null)}</strong>
                          {iface.required_signal_pins?.length ? (
                            <div>Pins: {iface.required_signal_pins.map(pin => `${pin.signal}(${pin.mcu_pin})`).join(", ")}</div>
                          ) : null}
                        </dd>
                      </div>
                    ))}
                    {selected.selected_profile && (
                      <div><dt>{zh ? "燒錄程序" : "Programming flow"}</dt><dd className="icSelectorProgramFlow">{selected.selected_profile.programming.program_model.normal_write_flow.join(" → ")}</dd></div>
                    )}
                  </dl>

                  {!selected.openocd_software_qualification.reviewed && (
                    <div className="icSelectorProfileUnavailable">
                      {selected.backend.mapping_status === "mapped"
                        ? (zh
                          ? "OpenOCD CFG 已存在，但此 exact ICPN 的 Phase 2 software qualification 仍為 UNKNOWN；CFG mapping 不能視為燒錄支援。"
                          : "An OpenOCD CFG mapping exists, but this exact ICPN remains UNKNOWN in Phase 2 software qualification; mapping alone is not programming support.")
                        : (zh
                          ? "此 exact ICPN 尚未完成 Phase 2 software qualification。"
                          : "This exact ICPN has not completed Phase 2 software qualification.")}
                    </div>
                  )}
                </>
              ) : selected.selected_profile ? (
                <dl>
                  <div><dt>{zh ? "Software Qualification" : "Software Qualification"}</dt><dd>{zh ? "Qualification evidence 未隨此部署提供" : "Qualification evidence is unavailable in this deployment"}</dd></div>
                  <div><dt>{zh ? "燒錄 VDD" : "Programming VDD"}</dt><dd>{voltageRange(selected.selected_profile.programming.electrical.vdd_programming_v)}</dd></div>
                  <div><dt>External VPP</dt><dd>{selected.selected_profile.programming.electrical.external_vpp?.required ? (zh ? "需要" : "Required") : (zh ? "不需要" : "Not required")}</dd></div>
                  {Object.entries(selected.selected_profile.programming.interfaces).map(([name, iface]) => (
                    <div key={name}>
                      <dt>{name}</dt>
                      <dd>
                        <strong>{iface.clock_hz ? formatClock(iface.clock_hz, zh) : humanizeStatus(iface.status ?? null)}</strong>
                        {iface.required_signal_pins?.length ? <div>Pins: {iface.required_signal_pins.map(pin => `${pin.signal}(${pin.mcu_pin})`).join(", ")}</div> : null}
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
                  {zh ? "此部署未提供 Phase 2 software qualification evidence；不能從 CFG mapping 推論燒錄支援。" : "Phase 2 software qualification evidence is unavailable in this deployment; programming support cannot be inferred from CFG mapping."}
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
              {selected.manufacturer_device_basic_profile && (
                <>
                  <div><dt>Device Basic Profile</dt><dd>{selected.manufacturer_device_basic_profile.profile_id}</dd></div>
                  <div><dt>{zh ? "Device Basic 來源" : "Device Basic source"}</dt><dd>ST official · {selected.manufacturer_device_basic_profile.evidence.observed_at_utc}</dd></div>
                </>
              )}
              <div><dt>OpenOCD</dt><dd>{backendLabel(selected.backend.mapping_status)}</dd></div>
              <div><dt>Target CFG</dt><dd><code>{selected.backend.target_config}</code></dd></div>
              <div><dt>Mapping</dt><dd>{humanizeStatus(selected.backend.mapping_method)}</dd></div>
              {selected.openocd_software_qualification && (
                <>
                  <div><dt>{zh ? "Software Qualification" : "Software Qualification"}</dt><dd><strong>{selected.openocd_software_qualification.software_state}</strong></dd></div>
                  <div><dt>{zh ? "Qualification Registry" : "Qualification Registry"}</dt><dd><code>{selected.openocd_software_qualification.registry_id}</code></dd></div>
                  {selected.openocd_software_qualification.provider && (
                    <>
                      <div><dt>{zh ? "Qualified Provider Commit" : "Qualified provider commit"}</dt><dd><code>{selected.openocd_software_qualification.provider.source_commit}</code></dd></div>
                      <div><dt>{zh ? "Qualified Runtime ID" : "Qualified runtime ID"}</dt><dd><code>{selected.openocd_software_qualification.provider.runtime_id}</code></dd></div>
                    </>
                  )}
                </>
              )}
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
              {selected.openocd_software_qualification?.software_state === "SUPPORTED"
                ? (zh
                  ? "此 exact ICPN 已完成 Phase 2 OpenOCD software qualification；這只代表軟體燒錄能力已證實，仍不代表 PPU、Site、Socket 或實體 IC 已完成 Phase 3 驗證。"
                  : "This exact ICPN has completed Phase 2 OpenOCD software qualification. This proves software programming capability only; PPU, Site, Socket, and real-IC Phase 3 validation remain separate.")
                : selected.openocd_software_qualification?.software_state === "UNKNOWN" && selected.backend.mapping_status === "mapped"
                  ? (zh
                    ? "OpenOCD CFG mapping 已存在，但此 exact ICPN 的 Phase 2 software qualification 仍為 UNKNOWN；不能把 CFG exists 解讀成已支援燒錄。"
                    : "An OpenOCD CFG mapping exists, but this exact ICPN remains UNKNOWN in Phase 2 software qualification; CFG existence is not programming support.")
                  : selected.backend_candidate
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
