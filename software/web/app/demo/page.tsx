"use client";

import Link from "next/link";
import { useI18n } from "../i18n";
import "./demo.css";

export default function DemoLandingPage() {
  const { t } = useI18n();

  return (
    <main className="demoLanding" data-route-marker="Choose a Demo">
      <section className="demoHero">
        <div className="demoBrand"><span>P</span><div><b>PLASMA</b><small>PROGRAMMING PLATFORM</small></div></div>
        <p className="demoEyebrow">{t("demo.eyebrow")}</p>
        <h1>{t("demo.title")}</h1>
        <p className="demoLead">{t("demo.lead")}</p>

        <div className="demoChoices">
          <Link className="demoCard fleet" href="/fleet">
            <div className="demoCardHead"><span>01</span><b>{t("mode.production")}</b></div>
            <h2>{t("demo.production.title")}</h2>
            <p>{t("demo.production.description")}</p>
            <dl><div><dt>{t("mode.label")}</dt><dd>production</dd></div><div><dt>Manager</dt><dd>{t("demo.production.manager")}</dd></div></dl>
            <strong>{t("demo.production.open")}</strong>
          </Link>

          <Link className="demoCard" href="/engineering">
            <div className="demoCardHead"><span>02</span><b>{t("mode.engineering")}</b></div>
            <h2>{t("demo.engineering.title")}</h2>
            <p>{t("demo.engineering.description")}</p>
            <dl><div><dt>{t("mode.label")}</dt><dd>engineering</dd></div><div><dt>PPU Console</dt><dd>{t("demo.engineering.ppuConsole")}</dd></div></dl>
            <strong>{t("demo.engineering.open")}</strong>
          </Link>
        </div>

        <div className="demoBoundary">
          <b>{t("demo.boundary.title")}</b>
          <span>{t("demo.boundary.description")}</span>
        </div>
      </section>
    </main>
  );
}
