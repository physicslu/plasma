"use client";

import { useEffect, useState } from "react";
import {
  getManagerPpuSites,
  type ManagerRegistryEntry,
} from "./ppu-registry-api";
import PpuSiteDesiredConfigurationCore from "./ppu-site-desired-configuration-core";
import PpuRuntimeActivation from "./ppu-runtime-activation";
import { isMissingSiteSettingsCapabilityRoute } from "./ppu-runtime-activation-capability";

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

type SiteDesiredCapabilityState = "checking" | "supported" | "unsupported";

function SiteDesiredCapabilityCard({ state }: { state: Exclude<SiteDesiredCapabilityState, "supported"> }) {
  const unsupported = state === "unsupported";
  return (
    <section className="ppuSiteCard" aria-label="Programming Site Configuration">
      <header className="ppuSiteCardHeader">
        <div>
          <h3>Programming Site Configuration</h3>
          <p className="ppuSiteHeaderNote">Site is the canonical independently controlled programming position inside a PPU. Topology is discovered from the PPU; this UI does not hard-code an eight-Site assumption.</p>
        </div>
        <span className="ppuReconciliationBadge" data-tone="muted">
          {unsupported ? "Not Supported" : "Checking"}
        </span>
      </header>

      <p className="ppuRegistryMessage warning" role="status">
        <strong>Site Desired Configuration:</strong>{" "}
        {unsupported
          ? "Not supported by this PPU profile. This is a capability boundary, not a runtime fault."
          : "Checking whether this PPU profile exposes Site Desired Configuration."}
      </p>

      {unsupported && (
        <p className="ppuSiteNote">This PPU profile does not expose Site Desired Configuration.</p>
      )}
    </section>
  );
}

export default function PpuSiteDesiredConfiguration(props: Props) {
  const alias = props.entry.alias;
  const [siteDesiredCapability, setSiteDesiredCapability] = useState<SiteDesiredCapabilityState>("checking");

  useEffect(() => {
    let cancelled = false;

    async function checkSiteDesiredCapability() {
      if (!alias) {
        if (!cancelled) setSiteDesiredCapability("supported");
        return;
      }

      setSiteDesiredCapability("checking");
      try {
        await getManagerPpuSites(alias);
        if (!cancelled) setSiteDesiredCapability("supported");
      } catch (error) {
        if (cancelled) return;
        // Only the exact legacy untyped missing-route 404 is a capability
        // boundary. Coded Manager 404s and transport/runtime failures remain
        // real errors and are delegated to the existing fail-closed core UI.
        setSiteDesiredCapability(isMissingSiteSettingsCapabilityRoute(error) ? "unsupported" : "supported");
      }
    }

    void checkSiteDesiredCapability();
    return () => {
      cancelled = true;
    };
  }, [alias]);

  return (
    <>
      {siteDesiredCapability === "supported"
        ? <PpuSiteDesiredConfigurationCore {...props} />
        : <SiteDesiredCapabilityCard state={siteDesiredCapability} />}
      <PpuRuntimeActivation {...props} />
    </>
  );
}
