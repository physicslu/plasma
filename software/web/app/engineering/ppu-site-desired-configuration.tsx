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

function SiteConfigurationCapabilitySummary({ state }: { state: Exclude<SiteDesiredCapabilityState, "supported"> }) {
  const unsupported = state === "unsupported";
  return (
    <section className="ppuSiteCard ppuCapabilitySummaryCard" aria-label="Programming configuration capabilities">
      <header className="ppuSiteCardHeader">
        <div>
          <small>CAPABILITIES</small>
          <h3>Programming Configuration</h3>
          <p className="ppuSiteHeaderNote">Observed Site topology is independent from configuration and Runtime-activation capability.</p>
        </div>
      </header>
      <div className="ppuCapabilitySummaryGrid">
        <div>
          <span>Site Desired Configuration</span>
          <strong>{unsupported ? "Not Supported" : "Checking"}</strong>
        </div>
        <div>
          <span>Runtime Activation</span>
          <strong>{unsupported ? "Not Supported" : "Checking"}</strong>
        </div>
      </div>
      <p className="ppuCapabilityBoundaryNote">
        {unsupported
          ? "This PPU profile exposes observed Sites but not the Site-settings route. This is a capability boundary, not a runtime fault."
          : "Checking whether this PPU profile exposes Site Desired Configuration and Runtime Activation."}
      </p>
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
      {siteDesiredCapability === "supported" ? (
        <>
          <PpuSiteDesiredConfigurationCore {...props} />
          <PpuRuntimeActivation {...props} />
        </>
      ) : (
        <SiteConfigurationCapabilitySummary state={siteDesiredCapability} />
      )}
    </>
  );
}
