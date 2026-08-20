"use client";

import { useState, useSyncExternalStore } from "react";
import { useI18n } from "../i18n";
import ProgrammingWorkspace from "./programming-workspace";
import "./engineering.css";
import "./engineering-log.css";

const sections = [
  ["overview", "engineering.overview"],
  ["ppu-sites", "engineering.ppuSites"],
  ["programming", "engineering.programming"],
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
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);
  const [active, setActive] = useState<(typeof sections)[number][0]>("overview");

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
                onClick={() => setActive(id)}
              >
                {t(key)}
              </button>
            ))}
          </nav>

          <section className={`engineeringCanvas ${active === "programming" ? "programmingActive" : ""}`}>
            {active === "programming" ? (
              <ProgrammingWorkspace />
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
