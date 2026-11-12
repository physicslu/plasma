export type ConsoleBuildIdentity = {
  productVersion: string;
  mode: "dev" | "build" | "unknown";
  gitSha: string | null;
  shortSha: string | null;
  releaseId: string | null;
  source: string;
  dirty: boolean;
};

export function inspectSourceGit(): { sha: string | null; dirty: boolean };

export function identityFromProvenance(args: {
  productVersion: string;
  mode: "dev" | "build";
  gitSha: string | null | undefined;
  dirty?: boolean;
  source?: string;
}): ConsoleBuildIdentity;

export function buildIdentityForVite(args: {
  mode: "dev" | "build";
  env?: Record<string, string | undefined>;
  gitProbe?: () => { sha: string | null; dirty: boolean };
}): ConsoleBuildIdentity;
