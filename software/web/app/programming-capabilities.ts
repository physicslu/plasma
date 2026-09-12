import type { EngineeringTargetCatalog } from "./plasma-api";

export type ProgrammingCapabilities = {
  synthetic_programming_image: boolean;
  target_device_required: boolean;
};

type CapabilityCatalog = EngineeringTargetCatalog & {
  programming_capabilities?: Partial<ProgrammingCapabilities>;
};

const FAIL_CLOSED_CAPABILITIES: ProgrammingCapabilities = {
  synthetic_programming_image: false,
  target_device_required: true,
};

const LEGACY_SHARED_MOCK_CAPABILITIES: ProgrammingCapabilities = {
  synthetic_programming_image: true,
  target_device_required: false,
};

export function resolveProgrammingCapabilities(
  catalog: EngineeringTargetCatalog | null | undefined,
): ProgrammingCapabilities {
  const advertised = (catalog as CapabilityCatalog | null | undefined)?.programming_capabilities;
  if (advertised) {
    return {
      synthetic_programming_image: advertised.synthetic_programming_image === true,
      target_device_required: advertised.target_device_required !== false,
    };
  }

  // Compatibility only for pre-capability legacy Shared Image Mock Gateways.
  // New PMode/EMode logic must consume capability semantics, not provider names.
  if (catalog?.provider === "mock") return LEGACY_SHARED_MOCK_CAPABILITIES;
  return FAIL_CLOSED_CAPABILITIES;
}
