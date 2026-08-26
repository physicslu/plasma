"use client";

import { useState, useSyncExternalStore } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import GatewaySettingsPanel from "./gateway-settings";
import MockRuntimeSettingsPanel from "./mock-runtime-settings";
import ProgrammingWorkspaceV2 from "./programming-workspace-v2";
import "./engineering.css";
import "./engineering-density.css";
import "./engineering-log.css";
import "./engineering-workspace-refresh.css";
import "./engineering-readability.css";
import "./engineering-alignment.css";

const sections = [
  ["overview", "engineering.overview", "⌂"],
  ["ppu-sites", "engineering.ppuSites", "▤"],
  ["programming", "engineering.programming", "▶"],
  ["mock", "engineering.settings", "◇"],
  ["diagnostics", "engineering.diagnostics", "∿"],
  ["logs", "engineering.logs", "▧"],
  ["tools", "engineering.tools", "⌘"],
  ["settings", "engineering.settings", "⚙"],
] as const;

function subscribeHydration(): () => void {
  return () => {};
}

export default function EngineeringPage() {
  const { t } = useI18n();
  const { emodeSection, setEmodeSection } = useWorkspaceSession();
  const [mockActive, setMockActive] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const active = mockActive ? "mock" : emodeSection;
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);
  const settingsSurfaceActive = active === "settings" || active === "mock";

  function selectSection(id: (typeof sections)[number][0]) {
    if (id === "mock") {
      setMockActive(true);
      return;
    }
    setMockActive(false);
    setEmodeSection(id);
  }

  return (
    <main className={`engineeringPage ${sidebarCollapsed ? "sidebarCollapsed" : ""}`}>
      <section className="engineeringShell">
        <div className="engineeringWorkspace">
          <aside className="engineeringSidebar">
            <header className="engineeringBrand">
              <span className="engineeringBrandMark" aria-hidden="true">⠿</span>
              <div>
                <strong>EMode</strong>
                <span>PLASMA</span>
                <h1>{t("engineering.title")}</h1>
              </div>
            </header>

            <nav aria-label={t("engineering.title")} aria-busy={!hydrated}>
              {sections.map(([id, key, icon]) => (
                <button
                  key={id}
                  type="button"
                  disabled={!hydrated}
                  className={active === id ? "active" : ""}
                  aria-pressed={active === id}
                  title={id === "mock" ? "Mock" : t(key)}
                  onClick={() => selectSection(id)}
                >
                  <span className="engineeringNavIcon" aria-hidden="true">{icon}</span>
                  <span className="engineeringNavLabel">{id === "mock" ? "Mock" : t(key)}</span>
                </button>
              ))}
            </nav>

            <button
              type="button"
              className="engineeringSidebarCollapse"
              aria-label={sidebarCollapsed ? "Expand Engineering menu" : "Collapse Engineering menu"}
              title={sidebarCollapsed ? "Expand" : "Collapse"}
              onClick={() => setSidebarCollapsed(value => !value)}
            >
              <span aria-hidden="true">{sidebarCollapsed ? "»" : "«"}</span>
              <span className="engineeringNavLabel">Collapse</span>
            </button>
          </aside>

          <section className={`engineeringCanvas ${active === "programming" ? "programmingActive" : settingsSurfaceActive ? "settingsActive" : ""}`}>
            {active === "programming" ? (
              <ProgrammingWorkspaceV2 />
            ) : active === "mock" ? (
              <MockRuntimeSettingsPanel />
            ) : active === "settings" ? (
              <GatewaySettingsPanel />
            ) : (
              <div className="engineeringPlaceholder">
                <small>EXTENSION SLOT</small>
                <h2>{t(sections.find(([id]) => id === active)?.[1] ?? "engineering.overview")}</h2>
                <p>{t("engineering.placeholder")}</p>
                <div className="engineeringSlotGrid" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
