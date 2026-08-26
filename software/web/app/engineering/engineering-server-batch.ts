"use client";

import { useSyncExternalStore } from "react";
import {
  beginBatchExecutionActivity,
  notifyBatchExecutionActivityChanged,
} from "../batch-execution-activity";
import {
  cancelServerBatch,
  createServerBatch,
  getServerBatch,
  ServerBatchApiError,
  terminalServerBatchStates,
  type CreateServerBatchOptions,
  type ServerBatchSnapshot,
} from "../server-batch-api";

export type EngineeringBatchCommandState = "idle" | "submitting" | "aborting";
export type EngineeringBatchObservationState = "connected" | "reconnecting";

export type EngineeringServerBatchState = {
  apiBase: string | null;
  snapshot: ServerBatchSnapshot | null;
  commandState: EngineeringBatchCommandState;
  observationState: EngineeringBatchObservationState;
  error: string | null;
};

type StoredBatch = {
  apiBase: string;
  batchId: string;
};

type Listener = () => void;

const ACTIVE_BATCH_STORAGE_KEY = "plasma-engineering-active-batch-v1";
const POLL_INTERVAL_MS = 250;
const POLL_LIMIT = 14_400;

let state: EngineeringServerBatchState = {
  apiBase: null,
  snapshot: null,
  commandState: "idle",
  observationState: "connected",
  error: null,
};
let observationGeneration = 0;
let activityRelease: (() => void) | null = null;
const listeners = new Set<Listener>();

function emit(): void {
  listeners.forEach(listener => listener());
}

function update(patch: Partial<EngineeringServerBatchState>): void {
  state = { ...state, ...patch };
  emit();
}

function readStoredBatch(): StoredBatch | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_BATCH_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredBatch>;
    if (typeof value.apiBase !== "string" || typeof value.batchId !== "string") return null;
    return { apiBase: value.apiBase, batchId: value.batchId };
  } catch {
    return null;
  }
}

function writeStoredBatch(apiBase: string, batchId: string): void {
  try {
    window.sessionStorage.setItem(
      ACTIVE_BATCH_STORAGE_KEY,
      JSON.stringify({ apiBase, batchId } satisfies StoredBatch),
    );
    notifyBatchExecutionActivityChanged();
  } catch {
    // sessionStorage is a reconnect hint only. The authoritative Batch remains server-owned.
  }
}

function clearStoredBatch(): void {
  try {
    window.sessionStorage.removeItem(ACTIVE_BATCH_STORAGE_KEY);
    notifyBatchExecutionActivityChanged();
  } catch {
    // Ignore storage failures; the in-memory lease still protects this document.
  }
}

function beginActivity(): void {
  if (activityRelease) return;
  activityRelease = beginBatchExecutionActivity();
}

function endActivity(): void {
  activityRelease?.();
  activityRelease = null;
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function publishSnapshot(apiBase: string, snapshot: ServerBatchSnapshot): boolean {
  const terminal = terminalServerBatchStates.has(snapshot.state);
  update({
    apiBase,
    snapshot,
    commandState: "idle",
    observationState: "connected",
    error: null,
  });
  if (terminal) {
    clearStoredBatch();
    endActivity();
  } else {
    writeStoredBatch(apiBase, snapshot.batch_id);
    beginActivity();
  }
  return terminal;
}

async function observe(apiBase: string, batchId: string, generation: number): Promise<void> {
  let consecutiveFailures = 0;
  for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
    if (generation !== observationGeneration) return;
    try {
      const snapshot = await getServerBatch(apiBase, batchId);
      if (generation !== observationGeneration) return;
      consecutiveFailures = 0;
      if (publishSnapshot(apiBase, snapshot)) return;
      await delay(POLL_INTERVAL_MS);
    } catch (error) {
      if (generation !== observationGeneration) return;
      if (error instanceof ServerBatchApiError && error.status === 404) {
        clearStoredBatch();
        endActivity();
        update({
          apiBase,
          snapshot: null,
          commandState: "idle",
          observationState: "connected",
          error: "Stored Engineering Batch no longer exists on the server",
        });
        return;
      }
      consecutiveFailures += 1;
      update({
        apiBase,
        observationState: "reconnecting",
        error: error instanceof Error ? error.message : "Engineering Batch observation failed",
      });
      await delay(Math.min(POLL_INTERVAL_MS * 2 ** Math.min(consecutiveFailures, 5), 5000));
    }
  }
  update({
    apiBase,
    observationState: "reconnecting",
    error: `Engineering Batch ${batchId} observation timed out`,
  });
}

function startObserver(apiBase: string, batchId: string): void {
  const generation = ++observationGeneration;
  void observe(apiBase, batchId, generation);
}

export function subscribeEngineeringServerBatch(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getEngineeringServerBatchState(): EngineeringServerBatchState {
  return state;
}

export function useEngineeringServerBatchState(): EngineeringServerBatchState {
  return useSyncExternalStore(
    subscribeEngineeringServerBatch,
    getEngineeringServerBatchState,
    getEngineeringServerBatchState,
  );
}

export async function restoreEngineeringServerBatch(apiBase: string): Promise<ServerBatchSnapshot | null> {
  const stored = readStoredBatch();
  if (!stored || stored.apiBase !== apiBase) return null;

  if (
    state.apiBase === apiBase
    && state.snapshot?.batch_id === stored.batchId
    && !terminalServerBatchStates.has(state.snapshot.state)
  ) {
    beginActivity();
    return state.snapshot;
  }

  beginActivity();
  update({ apiBase, commandState: "idle", observationState: "reconnecting", error: null });
  try {
    const snapshot = await getServerBatch(apiBase, stored.batchId);
    if (!publishSnapshot(apiBase, snapshot)) startObserver(apiBase, snapshot.batch_id);
    return snapshot;
  } catch (error) {
    if (error instanceof ServerBatchApiError && error.status === 404) {
      clearStoredBatch();
      endActivity();
      update({
        apiBase,
        snapshot: null,
        commandState: "idle",
        observationState: "connected",
        error: "Stored Engineering Batch no longer exists on the server",
      });
      return null;
    }
    update({
      apiBase,
      observationState: "reconnecting",
      error: error instanceof Error ? error.message : "Engineering Batch restore failed",
    });
    startObserver(apiBase, stored.batchId);
    return null;
  }
}

export async function startEngineeringServerBatch(
  apiBase: string,
  options: CreateServerBatchOptions,
): Promise<ServerBatchSnapshot> {
  if (state.snapshot && !terminalServerBatchStates.has(state.snapshot.state)) {
    throw new Error(`Engineering Batch ${state.snapshot.batch_id} is already active`);
  }

  ++observationGeneration;
  beginActivity();
  update({
    apiBase,
    snapshot: null,
    commandState: "submitting",
    observationState: "connected",
    error: null,
  });
  try {
    const snapshot = await createServerBatch(apiBase, options);
    if (!publishSnapshot(apiBase, snapshot)) startObserver(apiBase, snapshot.batch_id);
    return snapshot;
  } catch (error) {
    clearStoredBatch();
    endActivity();
    update({
      apiBase,
      snapshot: null,
      commandState: "idle",
      observationState: "connected",
      error: error instanceof Error ? error.message : "Engineering Batch submission failed",
    });
    throw error;
  }
}

export async function abortEngineeringServerBatch(apiBase: string): Promise<ServerBatchSnapshot | null> {
  const snapshot = state.snapshot;
  if (!snapshot || terminalServerBatchStates.has(snapshot.state)) return snapshot;
  if (state.commandState === "aborting") return snapshot;

  update({ commandState: "aborting", error: null });
  try {
    const next = await cancelServerBatch(apiBase, snapshot.batch_id);
    publishSnapshot(apiBase, next);
    return next;
  } catch (error) {
    update({
      commandState: "idle",
      error: error instanceof Error ? error.message : "Engineering Batch abort failed",
    });
    throw error;
  }
}

export function engineeringServerBatchStorageKey(): string {
  return ACTIVE_BATCH_STORAGE_KEY;
}
