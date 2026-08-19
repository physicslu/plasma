import type { Operation } from "./plasma-api";

export type BatchCommandPhase = "ready" | "submitting" | "active" | "terminal";

type BatchCommand = {
  phase: BatchCommandPhase;
  operation?: Operation;
  jobId?: string;
  cancelRequested?: boolean;
};

export type BatchCancelSnapshot = {
  submittingSites: number[];
  activeJobs: Array<[siteId: number, jobId: string]>;
};

export class BatchLifecycle {
  private cancelBarrier = false;
  private readonly commands: Record<number, BatchCommand>;

  constructor(siteIds: number[]) {
    this.commands = Object.fromEntries(
      siteIds.map(siteId => [siteId, { phase: "ready" as const }]),
    );
  }

  get cancelRequested(): boolean {
    return this.cancelBarrier;
  }

  isCancelRequested(siteId: number): boolean {
    return this.cancelBarrier || this.commands[siteId]?.cancelRequested === true;
  }

  prepare(siteId: number, operation: Operation): boolean {
    if (this.isCancelRequested(siteId)) {
      const command = this.commands[siteId] ?? { phase: "ready" as const };
      this.commands[siteId] = { ...command, phase: "terminal", operation };
      return false;
    }
    this.commands[siteId] = { phase: "ready", operation };
    return true;
  }

  beginSubmit(siteId: number): boolean {
    const command = this.commands[siteId];
    if (!command || this.isCancelRequested(siteId)) {
      if (command) this.commands[siteId] = { ...command, phase: "terminal" };
      return false;
    }
    this.commands[siteId] = { ...command, phase: "submitting" };
    return true;
  }

  canDispatch(siteId: number): boolean {
    return !this.isCancelRequested(siteId) && this.commands[siteId]?.phase === "submitting";
  }

  accepted(siteId: number, jobId: string): boolean {
    const command = this.commands[siteId] ?? { phase: "submitting" as const };
    this.commands[siteId] = { ...command, phase: "active", jobId };
    return this.isCancelRequested(siteId);
  }

  finish(siteId: number): void {
    const command = this.commands[siteId];
    if (!command) return;
    this.commands[siteId] = { ...command, phase: "terminal" };
  }

  cancelSite(siteId: number): string | undefined {
    const command = this.commands[siteId];
    if (!command) return undefined;
    this.commands[siteId] = { ...command, cancelRequested: true };
    if (command.phase === "active") return command.jobId;
    return undefined;
  }

  cancel(): BatchCancelSnapshot {
    this.cancelBarrier = true;
    const submittingSites: number[] = [];
    const activeJobs: Array<[number, string]> = [];

    for (const [siteIdText, command] of Object.entries(this.commands)) {
      const siteId = Number(siteIdText);
      if (command.phase === "submitting") submittingSites.push(siteId);
      if (command.phase === "active" && command.jobId) activeJobs.push([siteId, command.jobId]);
    }

    return { submittingSites, activeJobs };
  }
}
