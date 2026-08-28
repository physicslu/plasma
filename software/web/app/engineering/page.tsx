"use client";

import { useState, useSyncExternalStore } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import GatewaySettingsPanel from "./gateway-settings";
import MockRuntimeSettingsPanel from "./mock-runtime-settings";
import ProgrammingWorkspaceV2 from "./programming-workspace-v2";
import "./engineering.css";
import "./engineering-density.css";
import "./engineering-workspace-refresh.css";
import "./engineering-readability.css";
import "./engineering-alignment.css";

const sections = [
  ["overview", "engineering.overview", "⌂"],
  ["ppu-sites", "engineering.ppuSites", "▤"],
  ["programming", "engineering.programming", "▶"],
  ["diagnostics", "engineering.diagnostics", "∿"],
  ["logs", "engineering.logs", "▧"],
  ["tools", "engineering.tools", "⌘"],
  ["settings", "engineering.settings", "⚙"],
] as const;

type SettingsSection = "gateway" | "mock";

function subscribeHydration(): () => void {
  return () => {};
}

export default function EngineeringPage() {
  const { t } = useI18n();
  const { emodeSection, setEmodeSection } = useWorkspaceSession();
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("gateway");
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const active = emodeSection;
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);
  const settingsSurfaceActive = active === "settings";

  function selectSection(id: (typeof sections)[number][0]) {
    if (id === "settings") {
      setEmodeSection("settings");
      setSettingsExpanded(value => active === "settings" ? !value : true);
      return;
    }
    setEmodeSection(id);
  }

  function selectSettingsSection(id: SettingsSection) {
    setSettingsSection(id);
    setSettingsExpanded(true);
    setEmodeSection("settings");
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
              {sections.map(([id, key, icon]) => id === "settings" ? (
                <div className="engineeringNavTreeGroup" key={id}>
                  <button
                    type="button"
                    disabled={!hydrated}
                    className={active === id ? "active" : ""}
                    aria-pressed={active === id}
                    aria-expanded={settingsExpanded}
                    title={t(key)}
                    onClick={() => selectSection(id)}
                  >
                    <span className="engineeringNavIcon" aria-hidden="true">{icon}</span>
                    <span className="engineeringNavLabel">{t(key)}</span>
                    <span className="engineeringNavDisclosure" aria-hidden="true">{settingsExpanded ? "⌄" : "›"}</span>
                  </button>
                  {settingsExpanded && (
                    <div className="engineeringNavChildren" role="group" aria-label="Settings">
                      <button
                        type="button"
                        disabled={!hydrated}
                        className={settingsSurfaceActive && settingsSection === "gateway" ? "active" : ""}
                        aria-pressed={settingsSurfaceActive && settingsSection === "gateway"}
                        onClick={() => selectSettingsSection("gateway")}
                      >
                        <span className="engineeringNavTreeBranch" aria-hidden="true">├</span>
                        <span className="engineeringNavLabel">Gateway</span>
                      </button>
                      <button
                        type="button"
                        disabled={!hydrated}
                        className={settingsSurfaceActive && settingsSection === "mock" ? "active" : ""}
                        aria-pressed={settingsSurfaceActive && settingsSection === "mock"}
                        onClick={() => selectSettingsSection("mock")}
                      >
                        <span className="engineeringNavTreeBranch" aria-hidden="true">└</span>
                        <span className="engineeringNavLabel">Mock</span>
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <button
                  key={id}
                  type="button"
                  disabled={!hydrated}
                  className={active === id ? "active" : ""}
                  aria-pressed={active === id}
                  title={t(key)}
                  onClick={() => selectSection(id)}
                >
                  <span className="engineeringNavIcon" aria-hidden="true">{icon}</span>
                  <span className="engineeringNavLabel">{t(key)}</span>
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
            ) : active === "settings" && settingsSection === "mock" ? (
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
