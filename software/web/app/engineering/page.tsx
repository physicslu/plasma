"use client";

import { useState, useSyncExternalStore } from "react";
import { useI18n } from "../i18n";
import { useWorkspaceSession } from "../workspace-session";
import MockRuntimeSettingsPanel from "./mock-runtime-settings";
import ProgrammingWorkspaceV2 from "./programming-workspace-v2";
import "./engineering.css";
import "./engineering-density.css";
import "./engineering-log.css";

const sections = [
  ["overview", "engineering.overview"],
  ["ppu-sites", "engineering.ppuSites"],
  ["programming", "engineering.programming"],
  ["mock", "engineering.settings"],
  ["diagnostics", "engineering.diagnostics"],
  ["logs", "engineering.logs"],
  ["tools", "engineering.tools"],
  ["settings", "engineering.settings"],
] as const;

function subscribeHydration(): () => void {
  return () => {};
}

export default function EngineeringPage() {
  const { t } = useI18n();
  const { emodeSection, setEmodeSection } = useWorkspaceSession();
  const [mockActive, setMockActive] = useState(false);
  const active = mockActive ? "mock" : emodeSection;
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);

  function selectSection(id: (typeof sections)[number][0]) {
    if (id === "mock") {
      setMockActive(true);
      return;
    }
    setMockActive(false);
    setEmodeSection(id);
  }

  return (
    <main className="engineeringPage">
      <section className="engineeringShell">
        <header className="engineeringHeading">
          <p>PLASMA ENGINEERING WORKSPACE</p>
          <h1>{t("engineering.title")}</h1>
          <span>{t("engineering.subtitle")}</span>
        </header>

        <div className="engineeringWorkspace">
          <nav aria-label={t("engineering.title")} aria-busy={!hydrated}>
            {sections.map(([id, key]) => (
              <button
                key={id}
                type="button"
                disabled={!hydrated}
                className={active === id ? "active" : ""}
                aria-pressed={active === id}
                onClick={() => selectSection(id)}
              >
                {id === "mock" ? "Mock" : t(key)}
              </button>
            ))}
          </nav>

          <section className={`engineeringCanvas ${active === "programming" ? "programmingActive" : ""}`}>
            {active === "programming" ? (
              <ProgrammingWorkspaceV2 />
            ) : active === "mock" ? (
              <MockRuntimeSettingsPanel />
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
