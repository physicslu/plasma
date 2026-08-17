"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  cancelJob,
  DEFAULT_API_BASE,
  getChannels,
  getJob,
  normalizeApiBase,
  readDownloadUrl,
  startJob,
} from "./plasma-api";
import type { JobSnapshot, JobState, Operation } from "./plasma-api";

type Stage =
  | "idle"
  | "queued"
  | "erase"
  | "program"
  | "verify"
  | "read"
  | "success"
  | "cancelled"
  | "failed"
  | "timeout"
  | "aborted";
type Channel = {
  id: number;
  enabled: boolean;
  stage: Stage;
  progress: number;
  stageProgress: number;
  operation?: Operation;
  jobId?: string;
  file?: string;
  target?: string;
  interface?: string;
  error?: string;
  outputFile?: string;
};
type Theme = "dark" | "light";
type ConnectionState = "connecting" | "online" | "offline";
type BatchChannelState = "running" | "cancelling" | "success" | "cancelled" | "failed";

const MAX_FIRMWARE_BYTES = 16 * 1024 * 1024;
const BATCH_JOB_POLL_INTERVAL_MS = 500;
const BATCH_JOB_POLL_ATTEMPTS = 120;
const runningStages: Stage[] = ["queued", "erase", "program", "verify", "read"];
const failedStages: Stage[] = ["cancelled", "failed", "timeout", "aborted"];
const terminalJobStates = new Set<JobState>(["success", "failed", "cancelled", "timeout", "aborted"]);
const initialChannels: Channel[] = Array.from({ length: 8 }, (_, id) => ({
  id,
  enabled: id < 2,
  stage: "idle",
  progress: 0,
  stageProgress: 0,
}));
const stageLabels: Record<Stage, string> = {
  idle: "待命",
  queued: "排隊中",
  erase: "擦除中",
  program: "燒錄中",
  verify: "驗證中",
  read: "讀取中",
  success: "成功",
  cancelled: "已取消",
  failed: "失敗",
  timeout: "逾時",
  aborted: "已中止",
};
const batchStateLabels: Record<BatchChannelState, string> = {
  running: "執行中",
  cancelling: "取消中",
  success: "完成",
  cancelled: "已取消",
  failed: "失敗",
};
const operationLabels: Record<Operation, string> = {
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  read: "讀取",
};
const operationSymbols: Record<Operation, string> = {
  erase: "擦",
  program: "燒",
  verify: "驗",
  read: "讀",
};
const operationOrder = Object.keys(operationLabels) as Operation[];

function isRunning(channel: Channel): boolean {
  return runningStages.includes(channel.stage);
}

function uiStage(job: JobSnapshot): Stage {
  if (job.state === "running") {
    if (job.stage === "erase" || job.stage === "program" || job.stage === "verify" || job.stage?.startsWith("read_")) {
      return job.stage.startsWith("read_") ? "read" : job.stage;
    }
    return "queued";
  }
  if (job.state === "queued") return "queued";
  return job.state;
}

export default function Home() {
  const [channels, setChannels] = useState(initialChannels);
  const [visibleChannelIds, setVisibleChannelIds] = useState<number[]>([0, 1]);
  const [firmware, setFirmware] = useState<File | null>(null);
  const [readOffset, setReadOffset] = useState("0");
  const [readLength, setReadLength] = useState("256");
  const [selectedBatchOperations, setSelectedBatchOperations] = useState<Operation[]>([]);
  const [logs, setLogs] = useState<string[]>(["[SYSTEM] Plasma Web Console ready"]);
  const [detailsChannelId, setDetailsChannelId] = useState<number | null>(null);
  const [theme, setTheme] = useState<Theme>("light");
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_BASE);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [submittingChannelIds, setSubmittingChannelIds] = useState<number[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchCancelling, setBatchCancelling] = useState(false);
  const [batchChannelStates, setBatchChannelStates] = useState<Record<number, BatchChannelState>>({});
  const trackedJobs = useRef<Record<number, string>>({});
  const transitionKeys = useRef<Record<string, string>>({});
  const connectionRef = useRef<ConnectionState>("connecting");
  const batchCancelRequested = useRef(false);
  const batchActiveJobs = useRef<Record<number, string>>({});
  const cancelRequests = useRef<Set<string>>(new Set());

  const visibleChannels = channels.filter(channel => visibleChannelIds.includes(channel.id));
  const enabledCount = channels.filter(channel => channel.enabled).length;
  const disabledCount = channels.length - enabledCount;
  const detailsChannel = detailsChannelId === null
    ? undefined
    : channels.find(channel => channel.id === detailsChannelId);
  const detailsBatchState = detailsChannelId === null ? undefined : batchChannelStates[detailsChannelId];
  const readRangeValid = Number.isInteger(Number(readOffset))
    && Number(readOffset) >= 0
    && Number.isInteger(Number(readLength))
    && Number(readLength) > 0;

  const statusCounts = useMemo(() => visibleChannels.reduce((counts, channel) => {
    const batchState = batchChannelStates[channel.id];
    if (!channel.enabled) counts.disabled += 1;
    else if (batchState === "cancelling" || batchState === "cancelled") counts.cancelled += 1;
    else if (batchState === "running") counts.busy += 1;
    else if (batchState === "success") counts.success += 1;
    else if (batchState === "failed") counts.failed += 1;
    else if (submittingChannelIds.includes(channel.id) || isRunning(channel)) counts.busy += 1;
    else if (channel.stage === "success") counts.success += 1;
    else if (failedStages.includes(channel.stage)) counts.failed += 1;
    else counts.idle += 1;
    return counts;
  }, { idle: 0, busy: 0, success: 0, failed: 0, cancelled: 0, disabled: 0 }), [batchChannelStates, submittingChannelIds, visibleChannels]);

  const appendLog = useCallback((message: string) => {
    const time = new Date().toLocaleTimeString("zh-TW", { hour12: false });
    setLogs(items => [...items.slice(-80), `${time}  ${message}`]);
  }, []);

  const applyJob = useCallback((job: JobSnapshot) => {
    trackedJobs.current[job.channel_id] = job.job_id;
    const stage = uiStage(job);
    const error = job.result?.error?.message;
    const outputFile = job.result?.output_files?.[0]?.split(/[\\/]/).pop();
    setChannels(items => items.map(channel => channel.id === job.channel_id ? {
      ...channel,
      stage,
      operation: job.operation,
      progress: Number(job.progress_percent ?? 0),
      stageProgress: Number(job.stage_progress_percent ?? 0),
      jobId: job.job_id,
      error,
      outputFile,
    } : channel));

    const transitionKey = `${job.state}:${job.stage ?? "-"}`;
    if (transitionKeys.current[job.job_id] !== transitionKey) {
      transitionKeys.current[job.job_id] = transitionKey;
      appendLog(
        `[CH${job.channel_id}] ${job.job_id} · ${stageLabels[stage]}` +
        (error ? ` · ${error}` : ""),
      );
    }
  }, [appendLog]);

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("plasma-theme");
    const savedApi = window.localStorage.getItem("plasma-api-base");
    const restore = window.requestAnimationFrame(() => {
      if (savedTheme === "light" || savedTheme === "dark") setTheme(savedTheme);
      if (savedApi) {
        try {
          const normalized = normalizeApiBase(savedApi);
          setApiDraft(normalized);
          setApiBase(normalized);
        } catch {
          window.localStorage.removeItem("plasma-api-base");
        }
      }
    });
    return () => window.cancelAnimationFrame(restore);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("plasma-theme", theme);
  }, [theme]);

  useEffect(() => {
    let stopped = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const backendChannels = await getChannels(apiBase);
        if (stopped) return;
        setChannels(current => current.map(channel => {
          const backend = backendChannels.find(item => item.channel_id === channel.id);
          if (!backend) return channel;
          if (backend.current_job_id) trackedJobs.current[channel.id] = backend.current_job_id;
          return {
            ...channel,
            enabled: backend.enabled,
            target: backend.target ?? undefined,
            interface: backend.interface ?? undefined,
          };
        }));

        const jobs = await Promise.all(
          Object.values(trackedJobs.current).map(jobId => getJob(apiBase, jobId)),
        );
        if (stopped) return;
        jobs.forEach(applyJob);
        if (connectionRef.current !== "online") {
          connectionRef.current = "online";
          setConnection("online");
          appendLog(`[NET] Plasma Web REST Gateway connected · ${apiBase}`);
        }
      } catch (error) {
        if (stopped) return;
        if (connectionRef.current !== "offline") {
          connectionRef.current = "offline";
          setConnection("offline");
          appendLog(`[NET] Plasma Web REST Gateway offline · ${error instanceof Error ? error.message : "connection failed"}`);
        }
      } finally {
        if (!stopped) pollTimer = window.setTimeout(poll, 500);
      }
    }

    connectionRef.current = "connecting";
    void poll();
    return () => {
      stopped = true;
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [apiBase, appendLog, applyJob]);

  function connect(event: FormEvent) {
    event.preventDefault();
    try {
      const normalized = normalizeApiBase(apiDraft);
      window.localStorage.setItem("plasma-api-base", normalized);
      setApiDraft(normalized);
      connectionRef.current = "connecting";
      setConnection("connecting");
      setApiBase(normalized);
    } catch (error) {
      appendLog(`[NET] ${error instanceof Error ? error.message : "API URL 無效"}`);
    }
  }

  function setBatchChannelState(channelId: number, state: BatchChannelState) {
    setBatchChannelStates(current => ({ ...current, [channelId]: state }));
  }

  function clearBatchChannelState(channelId: number) {
    setBatchChannelStates(current => {
      if (!(channelId in current)) return current;
      const next = { ...current };
      delete next[channelId];
      return next;
    });
  }

  function channelDisplayState(channel: Channel): { state: Stage | "submitting"; label: string } {
    const batchState = batchChannelStates[channel.id];
    const submitting = submittingChannelIds.includes(channel.id);
    if (!channel.enabled) return { state: "idle", label: "停用" };
    if (batchState === "cancelling") return { state: "cancelled", label: "批次取消中" };
    if (batchState === "cancelled") return { state: "cancelled", label: "批次已取消" };
    if (batchState === "failed") return { state: "failed", label: "批次失敗" };
    if (batchState === "success") return { state: "success", label: "批次完成" };
    if (submitting) return { state: "submitting", label: "提交中" };
    if (batchState === "running" && channel.stage === "success") return { state: "queued", label: "批次進行中" };
    return { state: channel.stage, label: stageLabels[channel.stage] };
  }

  function toggleChannel(channelId: number) {
    const channel = channels[channelId];
    if (batchRunning || isRunning(channel) || submittingChannelIds.includes(channelId)) return;
    setVisibleChannelIds(current => {
      if (!current.includes(channelId)) return [...current, channelId].sort((left, right) => left - right);
      if (current.length === 1) {
        appendLog("[UI] 主畫面至少必須保留一個通道");
        return current;
      }
      return current.filter(id => id !== channelId);
    });
  }

  function operationDisabled(channel: Channel, operation: Operation, forBatch = false): boolean {
    if ((!forBatch && batchRunning) || connection !== "online" || !channel.enabled || isRunning(channel)) return true;
    if (submittingChannelIds.includes(channel.id)) return true;
    if ((operation === "program" || operation === "verify") && !firmware) return true;
    if ((operation === "program" || operation === "verify") && firmware.size > MAX_FIRMWARE_BYTES) return true;
    if (operation === "read" && !readRangeValid) return true;
    return false;
  }

  function batchDisabled(operation: Operation): boolean {
    return visibleChannels.some(channel => operationDisabled(channel, operation));
  }

  function toggleBatchOperation(operation: Operation) {
    if (batchRunning) return;
    setSelectedBatchOperations(current => {
      if (!current.includes(operation)) {
        return operationOrder.filter(item => current.includes(item) || item === operation);
      }
      return current.filter(item => item !== operation);
    });
  }

  async function runChannel(channelId: number, operation: Operation, forBatch = false): Promise<JobSnapshot | undefined> {
    const channel = channels[channelId];
    if (operationDisabled(channel, operation, forBatch)) return;
    if (firmware && firmware.size > MAX_FIRMWARE_BYTES) {
      appendLog(`[CH${channelId}] Firmware 超過 16 MiB 限制`);
      return;
    }

    if (!forBatch) clearBatchChannelState(channelId);
    setSubmittingChannelIds(current => current.includes(channelId) ? current : [...current, channelId]);
    try {
      const job = await startJob(apiBase, {
        channelId,
        operation,
        firmware: operation === "erase" || operation === "read" ? null : firmware,
        offset: operation === "read" ? Number(readOffset) : undefined,
        length: operation === "read" ? Number(readLength) : undefined,
      });
      trackedJobs.current[channelId] = job.job_id;
      setChannels(items => items.map(item => item.id === channelId ? {
        ...item,
        stage: "queued",
        operation,
        progress: 0,
        stageProgress: 0,
        jobId: job.job_id,
        file: firmware?.name,
        error: undefined,
        outputFile: undefined,
      } : item));
      appendLog(`[CH${channelId}] ${job.job_id} accepted by Python · ${operation.toUpperCase()}`);
      return job;
    } catch (error) {
      appendLog(`[CH${channelId}] Submit failed · ${error instanceof Error ? error.message : "unknown error"}`);
      setChannels(items => items.map(item => item.id === channelId ? {
        ...item,
        stage: "failed",
        operation,
        error: error instanceof Error ? error.message : "unknown error",
      } : item));
    } finally {
      setSubmittingChannelIds(current => current.filter(id => id !== channelId));
    }
  }

  async function waitForTerminalJob(job: JobSnapshot): Promise<JobSnapshot> {
    for (let attempt = 0; attempt < BATCH_JOB_POLL_ATTEMPTS; attempt += 1) {
      const current = await getJob(apiBase, job.job_id);
      applyJob(current);
      if (terminalJobStates.has(current.state)) return current;
      await new Promise(resolve => window.setTimeout(resolve, BATCH_JOB_POLL_INTERVAL_MS));
    }
    throw new Error(`${job.job_id} 等待完成逾時`);
  }

  async function requestJobCancel(channelId: number, jobId: string, fromBatch: boolean) {
    if (cancelRequests.current.has(jobId)) return;
    cancelRequests.current.add(jobId);
    try {
      await cancelJob(apiBase, jobId);
      appendLog(`[CH${channelId}] ${fromBatch ? "Batch cancel" : "Cancel"} requested · waiting for Python safe shutdown`);
    } catch (error) {
      cancelRequests.current.delete(jobId);
      appendLog(`[CH${channelId}] Cancel failed · ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  async function runBatch(operations: Operation[]) {
    if (batchRunning || operations.length === 0 || operations.some(batchDisabled)) return;
    const batchOperations = [...operations];
    const batchChannelIds = [...visibleChannelIds];
    batchCancelRequested.current = false;
    batchActiveJobs.current = {};
    setBatchChannelStates(batchChannelIds.reduce<Record<number, BatchChannelState>>((states, channelId) => {
      states[channelId] = "running";
      return states;
    }, {}));
    setBatchCancelling(false);
    setBatchRunning(true);
    appendLog(`[BATCH] START ${batchOperations.map(operation => operation.toUpperCase()).join(" → ")} · ${batchChannelIds.map(id => `CH${id}`).join(", ")}`);
    try {
      const outcomes = await Promise.all(batchChannelIds.map(async channelId => {
        for (const operation of batchOperations) {
          if (batchCancelRequested.current) {
            setBatchChannelState(channelId, "cancelled");
            appendLog(`[CH${channelId}] Batch stopped · CANCEL REQUESTED`);
            return { channelId, state: "cancelled" as const };
          }

          appendLog(`[CH${channelId}] Batch ${operation.toUpperCase()}`);
          const job = await runChannel(channelId, operation, true);
          if (!job) {
            const state = batchCancelRequested.current ? "cancelled" : "failed";
            setBatchChannelState(channelId, state);
            return { channelId, state };
          }
          batchActiveJobs.current[channelId] = job.job_id;

          if (batchCancelRequested.current) {
            await requestJobCancel(channelId, job.job_id, true);
          }

          try {
            const finalJob = await waitForTerminalJob(job);
            if (batchActiveJobs.current[channelId] === job.job_id) {
              delete batchActiveJobs.current[channelId];
            }

            const cancelWasRequested = batchCancelRequested.current || cancelRequests.current.has(job.job_id);
            if (cancelWasRequested) {
              setBatchChannelState(channelId, "cancelled");
              appendLog(`[CH${channelId}] Batch stopped · CANCEL REQUESTED · last job ${finalJob.state.toUpperCase()}`);
              return { channelId, state: "cancelled" as const };
            }
            if (finalJob.state === "cancelled") {
              setBatchChannelState(channelId, "cancelled");
              appendLog(`[CH${channelId}] Batch stopped · CANCELLED`);
              return { channelId, state: "cancelled" as const };
            }
            if (finalJob.state !== "success") {
              setBatchChannelState(channelId, "failed");
              appendLog(`[CH${channelId}] Batch stopped · ${finalJob.state.toUpperCase()}`);
              return { channelId, state: "failed" as const };
            }
          } catch (error) {
            if (batchActiveJobs.current[channelId] === job.job_id) {
              delete batchActiveJobs.current[channelId];
            }
            const cancelWasRequested = batchCancelRequested.current || cancelRequests.current.has(job.job_id);
            const state = cancelWasRequested ? "cancelled" : "failed";
            setBatchChannelState(channelId, state);
            appendLog(`[CH${channelId}] Batch polling failed · ${error instanceof Error ? error.message : "unknown error"}`);
            return { channelId, state };
          }
        }
        setBatchChannelState(channelId, "success");
        appendLog(`[CH${channelId}] Batch complete`);
        return { channelId, state: "success" as const };
      }));
      const successfulChannelIds = outcomes.filter(outcome => outcome.state === "success").map(outcome => outcome.channelId);
      const cancelledChannelIds = outcomes.filter(outcome => outcome.state === "cancelled").map(outcome => outcome.channelId);
      const failedChannelIds = outcomes.filter(outcome => outcome.state === "failed").map(outcome => outcome.channelId);
      const summary = `success: ${successfulChannelIds.length ? successfulChannelIds.map(id => `CH${id}`).join(", ") : "none"}`
        + (cancelledChannelIds.length ? ` · cancelled: ${cancelledChannelIds.map(id => `CH${id}`).join(", ")}` : "")
        + (failedChannelIds.length ? ` · failed: ${failedChannelIds.map(id => `CH${id}`).join(", ")}` : "");
      const batchOutcome = cancelledChannelIds.length ? "CANCELLED" : failedChannelIds.length ? "FAILED" : "COMPLETE";
      appendLog(`[BATCH] ${batchOutcome} · ${summary}`);
    } finally {
      batchActiveJobs.current = {};
      setBatchRunning(false);
      setBatchCancelling(false);
    }
  }

  async function cancelBatch() {
    if (!batchRunning || batchCancelling) return;
    batchCancelRequested.current = true;
    setBatchCancelling(true);
    setBatchChannelStates(current => Object.fromEntries(
      Object.entries(current).map(([channelId, state]) => [channelId, state === "running" ? "cancelling" : state]),
    ) as Record<number, BatchChannelState>);
    const activeJobs = Object.entries(batchActiveJobs.current);
    appendLog(`[BATCH] CANCEL requested · active jobs: ${activeJobs.length}`);
    await Promise.all(activeJobs.map(([channelId, jobId]) => requestJobCancel(Number(channelId), jobId, true)));
  }

  async function cancel(channelId: number) {
    const channel = channels[channelId];
    if (!channel.jobId || !isRunning(channel)) return;
    if (batchRunning && batchChannelStates[channelId] === "running") {
      setBatchChannelState(channelId, "cancelling");
    }
    await requestJobCancel(channelId, channel.jobId, false);
  }

  const batchTargetText = visibleChannelIds.length === 8
    ? "CH0～CH7"
    : visibleChannelIds.map(id => `CH${id}`).join("、");

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brandmark">P</span><div><b>PLASMA</b><small>PROGRAMMER CONTROL</small></div></div>
        <div className="topActions">
          <div className="themeSwitch" role="group" aria-label="介面主題">
            <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} aria-pressed={theme === "dark"}>深色</button>
            <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} aria-pressed={theme === "light"}>淺色</button>
          </div>
          <form className={`connection ${connection}`} onSubmit={connect}>
            <span className="pulse"/><div><b>Plasma Web REST Gateway</b><input aria-label="Plasma Web REST Gateway URL" value={apiDraft} onChange={event => setApiDraft(event.target.value)}/></div><button type="submit">連線</button>
          </form>
        </div>
      </header>

      <section className="console overviewConsole">
        <div className="pageHeading">
          <div><p className="eyebrow">CHANNEL MATRIX</p><h1>多通道工作總覽</h1></div>
          <div className={`gatewayHealth ${connection}`}><span className="pulse"/><div><small>Plasma Web REST Gateway</small><b>{connection === "online" ? "Online" : connection === "connecting" ? "Connecting" : "Offline"}</b></div><em>{enabledCount}/8 Enabled</em></div>
        </div>

        <section className="selectorPanel" aria-labelledby="channel-selector-title">
          <div className="sectionHeading">
            <div><p className="eyebrow">DISPLAY CHANNELS</p><h2 id="channel-selector-title">顯示與批次操作通道</h2></div>
            <div className="statusSummary" aria-label="通道配置摘要"><span>顯示 <b>{visibleChannelIds.length} / 8</b></span><span>停用 <b>{disabledCount}</b></span></div>
          </div>
          <div className="channelChecks">
            {channels.map(channel => {
              const locked = batchRunning || isRunning(channel) || submittingChannelIds.includes(channel.id);
              const displayState = channelDisplayState(channel);
              return <label key={channel.id} className={`${visibleChannelIds.includes(channel.id) ? "checked" : ""} ${!channel.enabled ? "disabled" : ""}`}>
                <input type="checkbox" aria-label={`顯示 CH${channel.id}`} checked={visibleChannelIds.includes(channel.id)} disabled={locked} onChange={() => toggleChannel(channel.id)}/>
                <span>CH{channel.id}</span><small>{displayState.label}</small>
              </label>;
            })}
          </div>
        </section>

        <section className="operationConfig" aria-label="工作參數">
          <div className="compactFile">
            <div><b>{firmware?.name ?? "選擇 Firmware BIN 檔案"}</b><small>{firmware ? `${(firmware.size / 1024).toFixed(1)} KB · BIN` : "Program / Verify 共用 · Max 16 MiB"}</small></div>
            <label>瀏覽檔案<input aria-label="選擇 Firmware 檔案" type="file" accept=".bin,application/octet-stream" disabled={batchRunning} onChange={event => setFirmware(event.target.files?.[0] ?? null)}/></label>
          </div>
          <div className="compactRead">
            <label>READ Offset<input aria-label="READ logical flash offset" type="number" min="0" step="1" value={readOffset} disabled={batchRunning} onChange={event => setReadOffset(event.target.value)}/></label>
            <label>READ Length<input aria-label="READ byte length" type="number" min="1" step="1" value={readLength} disabled={batchRunning} onChange={event => setReadLength(event.target.value)}/></label>
          </div>
        </section>

        <section className="batchPanel" aria-labelledby="batch-title">
          <div className="batchInfo">
            <div><p className="eyebrow">BATCH CONTROL</p><h2 id="batch-title">批次控制</h2><small>目標：{batchTargetText}</small></div>
            <div className="statusSummary" aria-label="選取通道狀態摘要">
              <span>待命 <b>{statusCounts.idle}</b></span><span className="busy">工作中 <b>{statusCounts.busy}</b></span><span className="success">成功 <b>{statusCounts.success}</b></span><span className="failed">取消 <b>{statusCounts.cancelled}</b></span><span className="failed">失敗 <b>{statusCounts.failed}</b></span>
            </div>
          </div>
          <div className="batchActions">
            <div className="batchOperationChoices" role="group" aria-label="選取批次操作">
              {operationOrder.map(operation => {
                const selected = selectedBatchOperations.includes(operation);
                return <label key={operation} className={selected ? "selected" : ""}>
                  <input type="checkbox" aria-label={`批次操作：${operationLabels[operation]}`} checked={selected} onChange={() => toggleBatchOperation(operation)} disabled={batchRunning}/>
                  <span>{operationSymbols[operation]}</span><b>{operationLabels[operation]}</b>
                </label>;
              })}
            </div>
            <div className="batchExecutionControls">
              <button type="button" className="executeBatch" aria-label={selectedBatchOperations.length ? `批次執行：${selectedBatchOperations.map(operation => operationLabels[operation]).join("、")}` : "批次執行：尚未選擇操作"} onClick={() => void runBatch(selectedBatchOperations)} disabled={batchRunning || selectedBatchOperations.length === 0 || selectedBatchOperations.some(batchDisabled)}><span>▶</span>{batchRunning ? "批次執行中" : `批次執行（${selectedBatchOperations.length}）`}</button>
              <button type="button" className="cancelBatch" aria-label="取消批次工作" onClick={() => void cancelBatch()} disabled={!batchRunning || batchCancelling}><span>■</span>{batchCancelling ? "取消中…" : "取消批次"}</button>
            </div>
          </div>
          {visibleChannels.some(channel => !channel.enabled) && <div className="warning">選取項目包含未啟用通道；取消勾選後才能執行批次工作。</div>}
          {firmware && firmware.size > MAX_FIRMWARE_BYTES && <div className="warning">Firmware 超過 16 MiB 限制。</div>}
        </section>

        <section className="overviewCard" aria-labelledby="overview-title">
          <div className="overviewHead"><div><p className="eyebrow">LIVE CHANNEL STATUS</p><h2 id="overview-title">通道執行狀態</h2></div><small>REST polling 500 ms</small></div>
          <div className="channelTableWrap">
            <table className="channelTable">
              <thead><tr><th>通道</th><th>目標／介面</th><th>目前工作</th><th>狀態</th><th>進度</th><th>獨立操作</th></tr></thead>
              <tbody>
                {visibleChannels.map(channel => {
                  const displayState = channelDisplayState(channel);
                  return <tr key={channel.id}>
                    <td><button className="channelDetails" onClick={() => setDetailsChannelId(channel.id)}><b>CH{channel.id}</b><small>詳細資料 ↗</small></button></td>
                    <td><b>{channel.target ?? "STM32F103C8T6"}</b><small>{channel.interface ?? "Mock / SWD"}</small></td>
                    <td>{channel.operation ? operationLabels[channel.operation] : "—"}{channel.error && <small className="errorText">{channel.error}</small>}</td>
                    <td><span className={`state ${displayState.state}`}>{displayState.label}</span></td>
                    <td><div className="tableProgress"><div className="track"><i style={{ width: `${channel.progress}%` }}/></div><b>{Math.round(channel.progress)}%</b></div></td>
                    <td><div className="rowActions">
                      {(Object.keys(operationLabels) as Operation[]).map(operation => <button key={operation} className={operation === "program" ? "primary" : ""} aria-label={`CH${channel.id} ${operationLabels[operation]}`} title={operationLabels[operation]} onClick={() => void runChannel(channel.id, operation)} disabled={operationDisabled(channel, operation)}>{operationSymbols[operation]}</button>)}
                      <button className="stop" aria-label={`取消 CH${channel.id} 工作`} title="取消工作" onClick={() => void cancel(channel.id)} disabled={!isRunning(channel)}>■</button>
                      {channel.stage === "success" && channel.jobId && channel.outputFile && <a className="rowDownload" aria-label={`下載 CH${channel.id} 讀取檔案`} title="下載 BIN" href={readDownloadUrl(apiBase, channel.jobId, channel.outputFile)}>↓</a>}
                    </div></td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="logCard">
          <div className="logHead"><div><span/>LIVE JOB LOG</div><button onClick={() => setLogs([])}>清除</button></div>
          <pre>{logs.length ? logs.join("\n") : "Log cleared."}</pre>
        </section>
      </section>

      {detailsChannel && <div className="modalBackdrop" onClick={() => setDetailsChannelId(null)}><section className="details" onClick={event => event.stopPropagation()}>
        <div className="detailsHead"><div><p className="eyebrow">JOB INSPECTOR</p><h2>Channel {detailsChannel.id} 詳細資料</h2></div><button aria-label="關閉詳細資料" onClick={() => setDetailsChannelId(null)}>×</button></div>
        <dl><div><dt>Plasma Web REST Gateway</dt><dd>{apiBase}</dd></div><div><dt>Job ID</dt><dd>{detailsChannel.jobId ?? "—"}</dd></div><div><dt>Operation</dt><dd>{detailsChannel.operation?.toUpperCase() ?? "—"}</dd></div><div><dt>Job State</dt><dd>{detailsChannel.stage.toUpperCase()}</dd></div><div><dt>Batch State</dt><dd>{detailsBatchState ? batchStateLabels[detailsBatchState] : "—"}</dd></div><div><dt>Firmware</dt><dd>{detailsChannel.file ?? "—"}</dd></div><div><dt>Progress</dt><dd>{detailsChannel.progress.toFixed(1)}%</dd></div><div><dt>Protocol</dt><dd>REST → Plasma v3.1 TCP</dd></div><div><dt>Target</dt><dd>{detailsChannel.target ?? "STM32F103C8T6"} ({detailsChannel.interface ?? "Mock"})</dd></div></dl>
        <p>Job State 保留 Python Job Manager 回傳的真實結果；Batch State 描述該通道在本次批次流程的結果。Mock 測試不代表 Z2、FPGA I/O 或實體 IC 已完成驗證。</p>
      </section></div>}
    </main>
  );
}
