"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  cancelJob,
  DEFAULT_API_BASE,
  getChannels,
  getJob,
  normalizeApiBase,
  startJob,
} from "./plasma-api";
import type { JobSnapshot, Operation } from "./plasma-api";

type Stage =
  | "idle"
  | "queued"
  | "erase"
  | "program"
  | "verify"
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
  jobId?: string;
  file?: string;
  target?: string;
  interface?: string;
  error?: string;
};
type Theme = "dark" | "light";
type ConnectionState = "connecting" | "online" | "offline";

const MAX_FIRMWARE_BYTES = 16 * 1024 * 1024;
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
  erase: "擦除",
  program: "燒錄",
  verify: "驗證",
  success: "完成",
  cancelled: "已取消",
  failed: "失敗",
  timeout: "逾時",
  aborted: "已中止",
};

function uiStage(job: JobSnapshot): Stage {
  if (job.state === "running") {
    if (job.stage === "erase" || job.stage === "program" || job.stage === "verify") {
      return job.stage;
    }
    return "queued";
  }
  if (job.state === "queued") return "queued";
  return job.state;
}

export default function Home() {
  const [channels, setChannels] = useState(initialChannels);
  const [selected, setSelected] = useState(0);
  const [firmware, setFirmware] = useState<File | null>(null);
  const [logs, setLogs] = useState<string[]>(["[SYSTEM] Plasma Web Console ready"]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("light");
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_BASE);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [submittingChannel, setSubmittingChannel] = useState<number | null>(null);
  const trackedJobs = useRef<Record<number, string>>({});
  const transitionKeys = useRef<Record<string, string>>({});
  const connectionRef = useRef<ConnectionState>("connecting");
  const active = channels[selected];
  const isRunning = ["queued", "erase", "program", "verify"].includes(active.stage);
  const enabledCount = channels.filter(channel => channel.enabled).length;

  const appendLog = useCallback((message: string) => {
    const time = new Date().toLocaleTimeString("zh-TW", { hour12: false });
    setLogs(items => [...items.slice(-80), `${time}  ${message}`]);
  }, []);

  const applyJob = useCallback((job: JobSnapshot) => {
    trackedJobs.current[job.channel_id] = job.job_id;
    const stage = uiStage(job);
    const error = job.result?.error?.message;
    setChannels(items => items.map(channel => channel.id === job.channel_id ? {
      ...channel,
      stage,
      progress: Number(job.progress_percent ?? 0),
      stageProgress: Number(job.stage_progress_percent ?? 0),
      jobId: job.job_id,
      error,
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
          appendLog(`[NET] Python Mock API connected · ${apiBase}`);
        }
      } catch (error) {
        if (stopped) return;
        if (connectionRef.current !== "offline") {
          connectionRef.current = "offline";
          setConnection("offline");
          appendLog(`[NET] Python API offline · ${error instanceof Error ? error.message : "connection failed"}`);
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

  async function run(requestedOperation: Operation | "sequence") {
    const operation: Operation = requestedOperation === "sequence" ? "program" : requestedOperation;
    if (!active.enabled || connection !== "online" || isRunning) return;
    if (operation !== "erase" && !firmware) return;
    if (firmware && firmware.size > MAX_FIRMWARE_BYTES) {
      appendLog(`[CH${selected}] Firmware 超過 16 MiB 限制`);
      return;
    }

    setSubmittingChannel(selected);
    try {
      const job = await startJob(apiBase, {
        channelId: selected,
        operation,
        firmware: operation === "erase" ? null : firmware,
      });
      trackedJobs.current[selected] = job.job_id;
      setChannels(items => items.map(channel => channel.id === selected ? {
        ...channel,
        stage: "queued",
        progress: 0,
        stageProgress: 0,
        jobId: job.job_id,
        file: firmware?.name,
        error: undefined,
      } : channel));
      appendLog(`[CH${selected}] ${job.job_id} accepted by Python · ${operation.toUpperCase()}`);
    } catch (error) {
      appendLog(`[CH${selected}] Submit failed · ${error instanceof Error ? error.message : "unknown error"}`);
    } finally {
      setSubmittingChannel(null);
    }
  }

  async function cancel() {
    if (!active.jobId || !isRunning) return;
    try {
      await cancelJob(apiBase, active.jobId);
      appendLog(`[CH${selected}] Cancel requested · waiting for Python safe shutdown`);
    } catch (error) {
      appendLog(`[CH${selected}] Cancel failed · ${error instanceof Error ? error.message : "unknown error"}`);
    }
  }

  const statusText = useMemo(() => {
    if (submittingChannel === selected) return "SUBMITTING";
    return active.stage === "idle" ? "READY" : active.stage.toUpperCase();
  }, [active.stage, selected, submittingChannel]);
  const controlDisabled = connection !== "online" || !active.enabled || isRunning || submittingChannel !== null;

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
            <span className="pulse"/><div><b>PYTHON MOCK API</b><input aria-label="Python API URL" value={apiDraft} onChange={event => setApiDraft(event.target.value)}/></div><button type="submit">連線</button>
          </form>
        </div>
      </header>

      <div className="workspace">
        <aside>
          <p className="eyebrow">CHANNEL MATRIX</p>
          <div className="channelGrid">
            {channels.map(channel => <button key={channel.id} onClick={() => setSelected(channel.id)} className={`channel ${selected === channel.id ? "selected" : ""} ${!channel.enabled ? "disabled" : ""}`}>
              <span>CH{channel.id}</span><i className={channel.stage}/><small>{channel.enabled ? stageLabels[channel.stage] : "DISABLED"}</small>
            </button>)}
          </div>
          <div className={`health ${connection}`}><span>PYTHON GATEWAY</span><b>{connection === "online" ? "Online" : connection === "connecting" ? "Connecting" : "Offline"}</b><div><i/><i/><i/><i/></div><small>{enabledCount}/8 channels enabled · REST polling 500 ms</small></div>
        </aside>

        <section className="console">
          <div className="heading"><div><p className="eyebrow">ACTIVE WORKSPACE</p><h1>Channel {selected}</h1></div><div className="headingActions"><button onClick={() => setDetailsOpen(true)}>詳細資料 ↗</button><span className={`state ${active.stage}`}>{statusText}</span></div></div>

          <div className="controlCard">
            <div className="fileDrop">
              <div className="chipIcon">⌁</div>
              <div><b>{firmware?.name ?? "選擇 Firmware BIN 檔案"}</b><small>{firmware ? `${(firmware.size / 1024).toFixed(1)} KB · BIN` : "支援 .bin · Max 16 MiB"}</small></div>
              <label>瀏覽檔案<input aria-label="選擇 Firmware 檔案" type="file" accept=".bin,application/octet-stream" onChange={event => setFirmware(event.target.files?.[0] ?? null)}/></label>
            </div>
            {!active.enabled && <div className="warning">CH{selected} 尚未在 Python Prototype 設定中啟用</div>}
            {connection !== "online" && <div className="warning">請先確認 Python Server 與 Gateway 已啟動，再連線 API</div>}
            {active.error && <div className="warning">{active.error}</div>}
            <div className="actions">
              <button onClick={() => void run("erase")} disabled={controlDisabled}><span>01</span>擦除<small>ERASE</small></button>
              <button onClick={() => void run("program")} disabled={controlDisabled || !firmware}><span>02</span>燒錄<small>PROGRAM</small></button>
              <button onClick={() => void run("verify")} disabled={controlDisabled || !firmware}><span>03</span>驗證<small>VERIFY</small></button>
              <button className="sequence" onClick={() => void run("sequence")} disabled={controlDisabled || !firmware}>執行完整流程 <b>→</b></button>
            </div>
          </div>

          <div className="progressCard">
            <div className="progressHead"><div><span className="ring">{Math.round(active.progress)}</span><div><b>{stageLabels[active.stage]}</b><small>{active.jobId ?? "尚未建立 Job"}</small></div></div><button className="cancel" onClick={() => void cancel()} disabled={!isRunning}>■　取消工作</button></div>
            <div className="track"><i style={{ width: `${active.progress}%` }}/></div>
            <div className="metrics"><span>整體進度 <b>{active.progress.toFixed(1)}%</b></span><span>階段進度 <b>{active.stageProgress.toFixed(1)}%</b></span><span>Firmware <b>{active.file ?? "—"}</b></span></div>
          </div>

          <div className="logCard">
            <div className="logHead"><div><span/>LIVE JOB LOG</div><button onClick={() => setLogs([])}>清除</button></div>
            <pre>{logs.length ? logs.join("\n") : "Log cleared."}</pre>
          </div>
        </section>
      </div>
      {detailsOpen && <div className="modalBackdrop" onClick={() => setDetailsOpen(false)}><section className="details" onClick={event => event.stopPropagation()}>
        <div className="detailsHead"><div><p className="eyebrow">JOB INSPECTOR</p><h2>Channel {selected} 詳細資料</h2></div><button aria-label="關閉詳細資料" onClick={() => setDetailsOpen(false)}>×</button></div>
        <dl><div><dt>Python API</dt><dd>{apiBase}</dd></div><div><dt>Job ID</dt><dd>{active.jobId ?? "—"}</dd></div><div><dt>Operation state</dt><dd>{active.stage.toUpperCase()}</dd></div><div><dt>Firmware</dt><dd>{active.file ?? "—"}</dd></div><div><dt>Protocol</dt><dd>REST → Plasma v3.1 TCP</dd></div><div><dt>Target</dt><dd>{active.target ?? "STM32F103C8T6"} ({active.interface ?? "Mock"})</dd></div></dl>
        <p>目前狀態由 Python Job Manager 與 MockInterface 回傳，不再由瀏覽器計時器產生。OpenOCD 與 FPGA 實機仍待後續驗證。</p>
      </section></div>}
    </main>
  );
}
