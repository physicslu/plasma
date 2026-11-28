import type { EngineeringTargetCatalog } from "./plasma-api";

export type ProgrammingCapabilities = {
  synthetic_programming_image: boolean;
  target_device_required: boolean;
};

export type ProgrammingCapabilityCatalog = EngineeringTargetCatalog & {
  programming_capabilities?: Partial<ProgrammingCapabilities> | null;
};
