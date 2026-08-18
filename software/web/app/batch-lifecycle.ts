import type { Operation } from "./plasma-api";

export type BatchCommandPhase = "ready" | "submitting" | "active" | "terminal";

type BatchCommand = {
  phase: BatchCommandPhase;
  operation?: Operation;
  jobId?: string;
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

  prepare(siteId: number, operation: Operation): boolean {
    if (this.cancelBarrier) {
      this.commands[siteId] = { phase: "terminal", operation };
      return false;
    }
    this.commands[siteId] = { phase: "ready", operation };
    return true;
  }

  beginSubmit(siteId: number): boolean {
    const command = this.commands[siteId];
    if (!command || this.cancelBarrier) {
      if (command) this.commands[siteId] = { ...command, phase: "terminal" };
      return false;
    }
    this.commands[siteId] = { ...command, phase: "submitting" };
    return true;
  }

  canDispatch(siteId: number): boolean {
    return !this.cancelBarrier && this.commands[siteId]?.phase === "submitting";
  }

  accepted(siteId: number, jobId: string): boolean {
    const command = this.commands[siteId] ?? { phase: "submitting" as const };
    this.commands[siteId] = { ...command, phase: "active", jobId };
    return this.cancelBarrier;
  }

  finish(siteId: number): void {
    const command = this.commands[siteId];
    if (!command) return;
    this.commands[siteId] = { ...command, phase: "terminal" };
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
