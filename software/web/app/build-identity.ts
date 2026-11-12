// Replaced by Vinext/Vite at build time for BOTH client and server bundles.
// Do not fetch a mutable runtime endpoint to guess which JS is executing.
export type ConsoleBuildIdentity = {
  productVersion: string;
  mode: "dev" | "build" | "unknown";
  gitSha: string | null;
  shortSha: string | null;
  releaseId: string | null;
  source: string;
  dirty: boolean;
};

declare const __PLASMA_BUILD_IDENTITY__: ConsoleBuildIdentity;

export const PLASMA_BUILD_IDENTITY: ConsoleBuildIdentity = __PLASMA_BUILD_IDENTITY__;

export function consoleBuildLabel(identity: ConsoleBuildIdentity): string {
  if (identity.mode === "dev") {
    return identity.dirty ? "DEV DIRTY" : identity.shortSha ? `DEV ${identity.shortSha}` : "DEV UNKNOWN";
  }
  return identity.mode === "build" && identity.shortSha
    ? `Build ${identity.shortSha}` : "Build UNKNOWN";
}

export function consoleBuildDetails(identity: ConsoleBuildIdentity): string {
  return [
    `Product Version: v${identity.productVersion}`,
    `Build Type: ${identity.mode.toUpperCase()}`,
    `Source SHA: ${identity.gitSha ?? "UNKNOWN"}`,
    `Release ID: ${identity.releaseId ?? "NOT AVAILABLE"}`,
    `Source: ${identity.source}`,
    ...(identity.dirty ? ["Uncommitted changes: YES (not an immutable release)"] : []),
  ].join("\n");
}
