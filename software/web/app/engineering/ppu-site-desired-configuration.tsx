"use client";

import type { ManagerRegistryEntry } from "./ppu-registry-api";
import PpuSiteDesiredConfigurationCore from "./ppu-site-desired-configuration-core";
import PpuRuntimeActivation from "./ppu-runtime-activation";

type Props = {
  entry: ManagerRegistryEntry;
  hasActiveExecution: boolean;
};

export default function PpuSiteDesiredConfiguration(props: Props) {
  return (
    <>
      <PpuSiteDesiredConfigurationCore {...props} />
      <PpuRuntimeActivation {...props} />
    </>
  );
}
