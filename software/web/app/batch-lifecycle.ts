import type { Operation } from "./plasma-api";

export type BatchCommandPhase = "ready" | "submitting" | "active" | "terminal";

type BatchCommand = {
  phase: BatchCommandPhase;
  operation?: Operation;
  jobId?: string;
};

export type BatchCancelSnapshot = {
  submittingChannels: number[];
  activeJobs: Array<[channelId: number, jobId: string]>;
};

export class BatchLifecycle {
  private cancelBarrier = false;
  private readonly commands: Record<number, BatchCommand>;

  constructor(channelIds: number[]) {
    this.commands = Object.fromEntries(
      channelIds.map(channelId => [channelId, { phase: "ready" as const }]),
    );
  }

  get cancelRequested(): boolean {
    return this.cancelBarrier;
  }

  prepare(channelId: number, operation: Operation): boolean {
    if (this.cancelBarrier) {
      this.commands[channelId] = { phase: "terminal", operation };
      return false;
    }
    this.commands[channelId] = { phase: "ready", operation };
    return true;
  }

  beginSubmit(channelId: number): boolean {
    const command = this.commands[channelId];
    if (!command || this.cancelBarrier) {
      if (command) this.commands[channelId] = { ...command, phase: "terminal" };
      return false;
    }
    this.commands[channelId] = { ...command, phase: "submitting" };
    return true;
  }

  canDispatch(channelId: number): boolean {
    return !this.cancelBarrier && this.commands[channelId]?.phase === "submitting";
  }

  accepted(channelId: number, jobId: string): boolean {
    const command = this.commands[channelId] ?? { phase: "submitting" as const };
    this.commands[channelId] = { ...command, phase: "active", jobId };
    return this.cancelBarrier;
  }

  finish(channelId: number): void {
    const command = this.commands[channelId];
    if (!command) return;
    this.commands[channelId] = { ...command, phase: "terminal" };
  }

  cancel(): BatchCancelSnapshot {
    this.cancelBarrier = true;
    const submittingChannels: number[] = [];
    const activeJobs: Array<[number, string]> = [];

    for (const [channelIdText, command] of Object.entries(this.commands)) {
      const channelId = Number(channelIdText);
      if (command.phase === "submitting") submittingChannels.push(channelId);
      if (command.phase === "active" && command.jobId) activeJobs.push([channelId, command.jobId]);
    }

    return { submittingChannels, activeJobs };
  }
}
