"use client";

import { useMemo, useState } from "react";
import "./ppu-site-configuration.css";

type PpuStatus = "Online" | "Pending" | "Offline" | "Disabled" | "Error";
type SiteStatus = "Ready" | "Running" | "Disabled" | "Error";

type PpuRecord = {
  id: string;
  name: string;
  location: string;
  status: PpuStatus;
  siteCount: number;
  gateway: string;
  model: string;
  serialNumber: string;
  firmwareVersion: string;
  registeredAt: string;
  capabilities: string[];
};

type DiscoveredPpu = {
  id: string;
  model: string;
  serialNumber: string;
  firmwareVersion: string;
  detectedAt: string;
  gateway: string;
  siteCount: number;
};

const initialPpus: PpuRecord[] = [
  {
    id: "PPU-001",
    name: "Line1-PPU-A",
    location: "Line 1 / Rack A",
    status: "Online",
    siteCount: 8,
    gateway: "192.168.10.21:18080",
    model: "PYNQ-Z2",
    serialNumber: "Z2-2026-0001",
    firmwareVersion: "0.9.0",
    registeredAt: "2026-09-02 10:03:11",
    capabilities: ["SWD", "SPI", "I2C", "GPIO"],
  },
  {
    id: "PPU-002",
    name: "Line1-PPU-B",
    location: "Line 1 / Rack B",
    status: "Online",
    siteCount: 4,
    gateway: "192.168.10.22:18080",
    model: "PYNQ-Z2",
    serialNumber: "Z2-2026-0002",
    firmwareVersion: "0.9.0",
    registeredAt: "2026-09-02 10:04:02",
    capabilities: ["SWD", "SPI", "I2C", "GPIO"],
  },
  {
    id: "PPU-003",
    name: "Line2-PPU-A",
    location: "Line 2 / Rack A",
    status: "Pending",
    siteCount: 8,
    gateway: "192.168.10.23:18080",
    model: "PYNQ-Z2",
    serialNumber: "Z2-2026-0003",
    firmwareVersion: "0.9.0",
    registeredAt: "2026-09-02 10:15:32",
    capabilities: ["SWD", "SPI", "I2C", "GPIO"],
  },
  {
    id: "PPU-004",
    name: "Line2-PPU-B",
    location: "Line 2 / Rack B",
    status: "Offline",
    siteCount: 2,
    gateway: "192.168.10.24:18080",
    model: "PYNQ-Z2",
    serialNumber: "Z2-2026-0004",
    firmwareVersion: "0.9.0",
    registeredAt: "2026-09-02 09:52:44",
    capabilities: ["SWD", "SPI", "I2C"],
  },
  {
    id: "PPU-005",
    name: "Disabled Unit",
    location: "Lab",
    status: "Disabled",
    siteCount: 8,
    gateway: "192.168.10.25:18080",
    model: "PYNQ-Z2",
    serialNumber: "Z2-2026-0005",
    firmwareVersion: "0.9.0",
    registeredAt: "2026-09-01 17:31:09",
    capabilities: ["SWD", "SPI", "I2C", "GPIO"],
  },
];

const initialDiscovered: DiscoveredPpu = {
  id: "PPU-006",
  model: "PYNQ-Z2",
  serialNumber: "Z2-2026-0006",
  firmwareVersion: "0.9.0",
  detectedAt: "2026-09-02 10:18:24",
  gateway: "192.168.10.26:18080",
  siteCount: 8,
};

function statusClass(status: PpuStatus | SiteStatus): string {
  return status.toLowerCase();
}

function buildInitialSiteEnableState(): Record<string, boolean[]> {
  return Object.fromEntries(initialPpus.map(ppu => [
    ppu.id,
    Array.from({ length: ppu.siteCount }, (_, index) => ppu.id === "PPU-003" ? ![4, 6].includes(index) : true),
  ]));
}

function siteStatus(ppu: PpuRecord, siteIndex: number, enabled: boolean): SiteStatus {
  if (!enabled) return "Disabled";
  if (ppu.status === "Offline" || ppu.status === "Disabled") return "Disabled";
  if (ppu.id === "PPU-003" && siteIndex === 2) return "Running";
  if (ppu.id === "PPU-003" && siteIndex === 3) return "Error";
  return "Ready";
}

export default function PpuSiteConfiguration() {
  const [ppus, setPpus] = useState<PpuRecord[]>(initialPpus);
  const [selectedPpuId, setSelectedPpuId] = useState("PPU-003");
  const [siteEnabledByPpu, setSiteEnabledByPpu] = useState<Record<string, boolean[]>>(buildInitialSiteEnableState);
  const [discovered, setDiscovered] = useState<DiscoveredPpu | null>(initialDiscovered);

  const selectedPpu = ppus.find(ppu => ppu.id === selectedPpuId) ?? ppus[0];
  const selectedSiteEnabled = siteEnabledByPpu[selectedPpu.id]
    ?? Array.from({ length: selectedPpu.siteCount }, () => true);
  const enabledSiteCount = selectedSiteEnabled.filter(Boolean).length;

  const statusCounts = useMemo(() => ({
    online: ppus.filter(ppu => ppu.status === "Online").length,
    pending: ppus.filter(ppu => ppu.status === "Pending").length,
    offline: ppus.filter(ppu => ppu.status === "Offline").length,
    disabled: ppus.filter(ppu => ppu.status === "Disabled").length,
  }), [ppus]);

  function updateSelectedPpu(patch: Partial<PpuRecord>) {
    setPpus(current => current.map(ppu => ppu.id === selectedPpu.id ? { ...ppu, ...patch } : ppu));
  }

  function setAllSites(enabled: boolean) {
    setSiteEnabledByPpu(current => ({
      ...current,
      [selectedPpu.id]: Array.from({ length: selectedPpu.siteCount }, () => enabled),
    }));
  }

  function toggleSite(index: number) {
    setSiteEnabledByPpu(current => {
      const previous = current[selectedPpu.id] ?? Array.from({ length: selectedPpu.siteCount }, () => true);
      return {
        ...current,
        [selectedPpu.id]: previous.map((enabled, siteIndex) => siteIndex === index ? !enabled : enabled),
      };
    });
  }

  function commissionSelected() {
    updateSelectedPpu({ status: "Online" });
  }

  function commissionDiscovered() {
    if (!discovered) return;
    const newPpu: PpuRecord = {
      id: discovered.id,
      name: discovered.id,
      location: "Unassigned",
      status: "Pending",
      siteCount: discovered.siteCount,
      gateway: discovered.gateway,
      model: discovered.model,
      serialNumber: discovered.serialNumber,
      firmwareVersion: discovered.firmwareVersion,
      registeredAt: discovered.detectedAt,
      capabilities: ["SWD", "SPI", "I2C", "GPIO"],
    };
    setPpus(current => [...current, newPpu]);
    setSiteEnabledByPpu(current => ({
      ...current,
      [newPpu.id]: Array.from({ length: newPpu.siteCount }, () => true),
    }));
    setSelectedPpuId(newPpu.id);
    setDiscovered(null);
  }

  return (
    <section className="ppuSiteConfiguration" aria-label="PPU and Site Configuration">
      <header className="ppuSiteHeader">
        <div>
          <small>PPU / SITE MANAGEMENT</small>
          <h2>PPU / Site Configuration</h2>
          <p>Commission PPU gateways and control which physical Sites are admitted for engineering and production use.</p>
        </div>
        <span className="ppuSiteManagerState">Manager Online</span>
      </header>

      <div className="ppuSiteLayout">
        <div className="ppuSiteColumn">
          <section className="ppuSiteCard" aria-label="PPU List">
            <header className="ppuSiteCardHeader">
              <h3>PPU List</h3>
              <button className="ppuSiteButton primary" type="button">Scan for New PPU</button>
            </header>

            <div className="ppuSiteFilters" aria-label="PPU status summary">
              <span className="ppuSiteFilter">All {ppus.length}</span>
              <span className="ppuSiteFilter" data-tone="online">Online {statusCounts.online}</span>
              <span className="ppuSiteFilter" data-tone="pending">Pending {statusCounts.pending}</span>
              <span className="ppuSiteFilter">Offline {statusCounts.offline}</span>
              <span className="ppuSiteFilter">Disabled {statusCounts.disabled}</span>
            </div>

            <div className="ppuTableWrap">
              <table className="ppuTable">
                <thead>
                  <tr>
                    <th>PPU ID</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Sites</th>
                    <th>Gateway</th>
                  </tr>
                </thead>
                <tbody>
                  {ppus.map(ppu => (
                    <tr
                      key={ppu.id}
                      className={ppu.id === selectedPpu.id ? "selected" : ""}
                      onClick={() => setSelectedPpuId(ppu.id)}
                    >
                      <td><span className="ppuIdLink">{ppu.id}</span></td>
                      <td>{ppu.name}</td>
                      <td><span className={`ppuSiteStatus ${statusClass(ppu.status)}`}>{ppu.status}</span></td>
                      <td>{ppu.siteCount}</td>
                      <td>{ppu.gateway}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="ppuSiteCard" aria-label="New or discovered PPU">
            <header className="ppuSiteCardHeader">
              <h3>New / Discovered PPU</h3>
              <span className="ppuSiteFilter">{discovered ? 1 : 0}</span>
            </header>
            <div className="ppuDiscoveredBody">
              {discovered ? (
                <article className="ppuDiscoveredItem">
                  <div className="ppuDiscoveredTop">
                    <div>
                      <strong>{discovered.id}</strong>
                      <span className="ppuNewBadge">New</span>
                    </div>
                    <div className="ppuSiteCardHeaderActions">
                      <button className="ppuSiteButton primary" type="button" onClick={commissionDiscovered}>Commission</button>
                      <button className="ppuSiteButton" type="button" onClick={() => setDiscovered(null)}>Ignore</button>
                    </div>
                  </div>
                  <div className="ppuMetaGrid">
                    <div><span>Model</span><strong>{discovered.model}</strong></div>
                    <div><span>Serial Number</span><strong>{discovered.serialNumber}</strong></div>
                    <div><span>FW Version</span><strong>{discovered.firmwareVersion}</strong></div>
                    <div><span>Detected At</span><strong>{discovered.detectedAt}</strong></div>
                    <div><span>Gateway Endpoint</span><strong>{discovered.gateway}</strong></div>
                    <div><span>Reported Sites</span><strong>{discovered.siteCount}</strong></div>
                  </div>
                  <p className="ppuSiteNote"><strong>Pending admission:</strong> review identity and topology before this PPU becomes available to PMode.</p>
                </article>
              ) : (
                <p className="ppuSiteNote">No uncommissioned PPU is currently waiting for review.</p>
              )}
            </div>
          </section>
        </div>

        <div className="ppuSiteColumn">
          <section className="ppuSiteCard" aria-label="PPU Information">
            <header className="ppuSiteCardHeader">
              <div className="ppuSiteCardHeaderActions">
                <h3>{selectedPpu.id}</h3>
                <span className={`ppuSiteStatus ${statusClass(selectedPpu.status)}`}>{selectedPpu.status}</span>
              </div>
              <div className="ppuSiteCardHeaderActions">
                {selectedPpu.status === "Pending" && (
                  <button className="ppuSiteButton primary" type="button" onClick={commissionSelected}>Commission</button>
                )}
                <button
                  className="ppuSiteButton danger"
                  type="button"
                  onClick={() => updateSelectedPpu({ status: selectedPpu.status === "Disabled" ? "Offline" : "Disabled" })}
                >
                  {selectedPpu.status === "Disabled" ? "Enable" : "Disable"}
                </button>
                <button className="ppuSiteButton" type="button">Health Check</button>
              </div>
            </header>

            <div className="ppuInfoBody">
              <dl className="ppuInfoGrid">
                <div><dt>PPU ID</dt><dd>{selectedPpu.id}</dd></div>
                <div><dt>Status</dt><dd><span className={`ppuSiteStatus ${statusClass(selectedPpu.status)}`}>{selectedPpu.status}</span></dd></div>
                <div><dt>HW Model</dt><dd>{selectedPpu.model}</dd></div>
                <div><dt>FW Version</dt><dd>{selectedPpu.firmwareVersion}</dd></div>

                <div className="wide">
                  <dt>Name</dt>
                  <dd><input className="ppuEditable" value={selectedPpu.name} onChange={event => updateSelectedPpu({ name: event.target.value })} /></dd>
                </div>
                <div className="wide">
                  <dt>Location</dt>
                  <dd><input className="ppuEditable" value={selectedPpu.location} onChange={event => updateSelectedPpu({ location: event.target.value })} /></dd>
                </div>

                <div className="wide"><dt>Gateway Endpoint</dt><dd>{selectedPpu.gateway}</dd></div>
                <div><dt>Plasma Server</dt><dd><span className="ppuSiteStatus online">Online</span></dd></div>
                <div><dt>Gateway</dt><dd><span className="ppuSiteStatus online">Online</span></dd></div>
                <div className="wide"><dt>Serial Number</dt><dd>{selectedPpu.serialNumber}</dd></div>
                <div className="wide"><dt>Manager Registered At</dt><dd>{selectedPpu.registeredAt}</dd></div>
                <div className="wide">
                  <dt>Capabilities</dt>
                  <dd className="ppuCapabilityList">
                    {selectedPpu.capabilities.map(capability => <span className="ppuCapabilityTag" key={capability}>{capability}</span>)}
                  </dd>
                </div>
              </dl>
            </div>
          </section>

          <section className="ppuSiteCard" aria-label="Site Configuration">
            <header className="ppuSiteCardHeader">
              <h3>Site Configuration</h3>
              <div className="ppuSiteCardHeaderActions">
                <button className="ppuSiteButton primary" type="button" onClick={() => setAllSites(true)}>Enable All</button>
                <button className="ppuSiteButton" type="button" onClick={() => setAllSites(false)}>Disable All</button>
              </div>
            </header>

            <div className="ppuSiteSummary">
              <span>Physical Sites <strong>{selectedPpu.siteCount}</strong></span>
              <span>Enabled Sites <strong>{enabledSiteCount}</strong></span>
              <span>Disabled Sites <strong>{selectedPpu.siteCount - enabledSiteCount}</strong></span>
            </div>

            <div className="ppuTableWrap">
              <table className="ppuTable">
                <thead>
                  <tr>
                    <th>Site ID</th>
                    <th>Site Name</th>
                    <th>Enabled</th>
                    <th>Status</th>
                    <th>Capability</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: selectedPpu.siteCount }, (_, index) => {
                    const enabled = selectedSiteEnabled[index] ?? true;
                    const status = siteStatus(selectedPpu, index, enabled);
                    return (
                      <tr key={`${selectedPpu.id}-site-${index}`}>
                        <td><span className="ppuIdLink">SITE{index}</span></td>
                        <td>Socket-A{index + 1}</td>
                        <td>
                          <input
                            className="ppuSiteToggle"
                            aria-label={`Enable SITE${index}`}
                            type="checkbox"
                            checked={enabled}
                            onChange={() => toggleSite(index)}
                          />
                        </td>
                        <td><span className={`ppuSiteStatus ${statusClass(status)}`}>{status}</span></td>
                        <td>{selectedPpu.capabilities.filter(capability => capability !== "GPIO").join(" / ")}</td>
                        <td>{status === "Error" ? "Comm. Timeout" : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <p className="ppuSiteNote">
              <strong>Ownership boundary:</strong> physical Site count and capabilities are reported by the PPU. The Console only controls admission and logical naming; PL/AXI resource mapping remains PPU-owned.
            </p>
          </section>
        </div>
      </div>
    </section>
  );
}
