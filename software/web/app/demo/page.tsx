"use client";

import Link from "next/link";
import { useI18n } from "../i18n";
import "./demo.css";

export default function DemoLandingPage() {
  const { locale, t } = useI18n();
  const zh = locale === "zh-TW";

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
            <strong>{t("demo.production.open")}</strong>
          </Link>

          <Link className="demoCard" href="/engineering">
            <div className="demoCardHead"><span>02</span><b>{t("mode.engineering")}</b></div>
            <h2>{t("demo.engineering.title")}</h2>
            <p>{t("demo.engineering.description")}</p>
            <strong>{t("demo.engineering.open")}</strong>
          </Link>

          <Link className="demoCard utility" href="/devices">
            <div className="demoCardHead"><span>03</span><b>{zh ? "料號查詢" : "IC LOOKUP"}</b></div>
            <h2>IC Selector</h2>
            <p>
              {zh
                ? "直接輸入 ICPN／IC identifier 查詢 Vendor、Family、OCD mapping 與目前可用的驗證證據。"
                : "Search an ICPN or IC identifier directly for Vendor, Family, OCD mapping, and currently available validation evidence."}
            </p>
            <strong>{zh ? "查詢 IC 料號 →" : "Open IC Selector →"}</strong>
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
