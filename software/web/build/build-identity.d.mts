export type ConsoleBuildIdentity = {
  productVersion: string;
  mode: "dev" | "build" | "unknown";
  gitSha: string | null;
  shortSha: string | null;
  releaseId: string | null;
  source: string;
  dirty: boolean;
  failureReason?: string;
};

export function inspectSourceGit(): {
  sha: string | null; dirty: boolean;
  headState: "ok" | "timeout" | "error" | "invalid";
  statusState: "ok" | "timeout" | "error";
  trackedModified: number; untracked: number;
};

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
  requireGitCheckout?: boolean;
}): ConsoleBuildIdentity;
