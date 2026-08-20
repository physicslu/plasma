"use client";

import { useMemo, useState } from "react";
import SinglePPUConsole from "../page";

type TargetSource = "local" | "simulation";

type SimulatedPPU = {
  ppuId: string;
  displayName: string;
  siteCount: number;
};

type SimulatedFacility = {
  facilityId: string;
  displayName: string;
  ppus: SimulatedPPU[];
};

const simulatedFacilities: SimulatedFacility[] = Array.from({ length: 3 }, (_, facilityIndex) => {
  const facilityNumber = facilityIndex + 1;
  const facilityId = `facility-${String(facilityNumber).padStart(2, "0")}`;
  return {
    facilityId,
    displayName: `Facility ${String(facilityNumber).padStart(2, "0")}`,
    ppus: [2, 4, 6, 8].map((siteCount, ppuIndex) => ({
      ppuId: `${facilityId}-ppu-${String(ppuIndex + 1).padStart(2, "0")}`,
      displayName: `PPU ${String(ppuIndex + 1).padStart(2, "0")}`,
      siteCount,
    })),
  };
});

const operations = [
  ["E", "Erase"],
  ["P", "Program"],
  ["V", "Verify"],
  ["R", "Read"],
] as const;

export default function ProgrammingWorkspace() {
  const [source, setSource] = useState<TargetSource>("local");
  const [facilityId, setFacilityId] = useState(simulatedFacilities[0].facilityId);
  const [ppuIndex, setPPUIndex] = useState(0);

  const facility = useMemo(
    () => simulatedFacilities.find(item => item.facilityId === facilityId) ?? simulatedFacilities[0],
    [facilityId],
  );
  const ppu = facility.ppus[ppuIndex] ?? facility.ppus[0];
  const simulatedSites = Array.from({ length: ppu.siteCount }, (_, index) => index + 1);

  return (
    <section className="engineeringProgramming" aria-label="Engineering programming workspace">
      <div className="engineeringProgrammingHeader">
        <div>
          <p>ENGINEERING / PROGRAMMING</p>
          <h2>Single PPU Programming</h2>
          <span>單台 PPU 的 Erase / Program / Verify / Read 工程驗證工作台。</span>
        </div>
        <div className="targetSourceSwitch" role="group" aria-label="Programming target source">
          <button
            type="button"
            className={source === "local" ? "active" : ""}
            aria-pressed={source === "local"}
            onClick={() => setSource("local")}
          >
            Connected Local PPU
          </button>
          <button
            type="button"
            className={source === "simulation" ? "active" : ""}
            aria-pressed={source === "simulation"}
            onClick={() => setSource("simulation")}
          >
            Simulation Catalog
          </button>
        </div>
      </div>

      {source === "local" ? (
        <div className="engineeringProgrammingLocal" data-target-source="local">
          <div className="engineeringBoundaryNote">
            <b>LOCAL EXECUTION</b>
            <span>此區直接重用既有單 PPU Console；工作只送往目前設定的 PPU-local Plasma Web REST Gateway。</span>
          </div>
          <SinglePPUConsole />
        </div>
      ) : (
        <div className="engineeringSimulation" data-target-source="simulation">
          <div className="engineeringTargetSelector">
            <label>
              <span>Facility</span>
              <select
                aria-label="Engineering Facility"
                value={facility.facilityId}
                onChange={event => {
                  setFacilityId(event.target.value);
                  setPPUIndex(0);
                }}
              >
                {simulatedFacilities.map(item => (
                  <option key={item.facilityId} value={item.facilityId}>{item.displayName}</option>
                ))}
              </select>
            </label>
            <label>
              <span>PPU</span>
              <select
                aria-label="Engineering PPU"
                value={String(ppuIndex)}
                onChange={event => setPPUIndex(Number(event.target.value))}
              >
                {facility.ppus.map((item, index) => (
                  <option key={item.ppuId} value={String(index)}>
                    {item.displayName} — {item.siteCount} Sites
                  </option>
                ))}
              </select>
            </label>
            <div className="engineeringTargetIdentity" aria-label="Selected simulated PPU">
              <span className="simulationBadge">SIMULATED</span>
              <b>{facility.displayName} / {ppu.displayName}</b>
              <small>{ppu.ppuId} · {ppu.siteCount} Sites</small>
            </div>
          </div>

          <div className="engineeringBoundaryNote warning">
            <b>NO HARDWARE EXECUTION</b>
            <span>Simulation Catalog 只驗證 Facility / PPU / Site 拓樸與 Engineering UI。它不會把 E/P/V/R 送到 Local PPU，也不經由目前 read-only 的 Manager 執行遠端寫入。</span>
          </div>

          <section className="simulatedSitePanel" aria-labelledby="simulated-site-title">
            <div className="simulatedSiteHeading">
              <div>
                <p>SITE TOPOLOGY</p>
                <h3 id="simulated-site-title">{ppu.displayName} Programming Sites</h3>
              </div>
              <span>Sites <b>{ppu.siteCount}</b></span>
            </div>
            <div className="simulatedSiteGrid" aria-label="Simulated site topology">
              {simulatedSites.map(siteId => (
                <article key={siteId} className="simulatedSiteCard">
                  <div>
                    <b>SITE {siteId}</b>
                    <span>IDLE · SIMULATED</span>
                  </div>
                  <div className="simulatedOperations" aria-label={`SITE ${siteId} simulated operations`}>
                    {operations.map(([code, label]) => (
                      <button
                        key={code}
                        type="button"
                        aria-label={`SITE ${siteId} ${label} simulated`}
                        title={`${label} is disabled for simulated targets`}
                        disabled
                      >
                        <b>{code}</b>
                        <span>{label}</span>
                      </button>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
