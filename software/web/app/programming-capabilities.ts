import type { EngineeringTargetCatalog } from "./plasma-api";

export type ProgrammingCapabilities = {
  synthetic_programming_image: boolean;
  target_device_required: boolean;
};

export type ProgrammingCapabilityCatalog = EngineeringTargetCatalog & {
  programming_capabilities?: Partial<ProgrammingCapabilities> | null;
};

const FAIL_CLOSED_CAPABILITIES: ProgrammingCapabilities = {
  synthetic_programming_image: false,
  target_device_required: true,
};

export function resolveProgrammingCapabilities(
  catalog: ProgrammingCapabilityCatalog | null | undefined,
): ProgrammingCapabilities {
  const advertised = catalog?.programming_capabilities;
  if (
    !advertised
    || typeof advertised.synthetic_programming_image !== "boolean"
    || typeof advertised.target_device_required !== "boolean"
  ) {
    return FAIL_CLOSED_CAPABILITIES;
  }

  return {
    synthetic_programming_image: advertised.synthetic_programming_image,
    target_device_required: advertised.target_device_required,
  };
}
