"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Stage = "idle" | "erase" | "program" | "verify" | "success" | "cancelled";
type Channel = { id: number; stage: Stage; progress: number; stageProgress: number; jobId?: string; file?: string };
type Theme = "dark" | "light";

const initialChannels: Channel[] = Array.from({ length: 8 }, (_, id) => ({ id, stage: "idle", progress: 0, stageProgress: 0 }));
const stageLabels: Record<Stage, string> = { idle: "待命", erase: "擦除", program: "燒錄", verify: "驗證", success: "完成", cancelled: "已取消" };

export default function Home() {
  const [channels, setChannels] = useState(initialChannels);
  const [selected, setSelected] = useState(0);
  const [firmware, setFirmware] = useState<File | null>(null);
  const [logs, setLogs] = useState<string[]>(["18:42:06  [SYSTEM]  Plasma Web Console ready", "18:42:06  [NET]     Programmer PYNQ-001 connected · 2 active channels"]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("dark");
  const timers = useRef<Record<number, ReturnType<typeof setInterval>>>({});
  const active = channels[selected];
  const enabled = selected < 2;
  const isRunning = (["erase", "program", "verify"] as Stage[]).includes(active.stage);

  useEffect(() => {
    const saved = window.localStorage.getItem("plasma-theme");
    const restoreTheme = window.requestAnimationFrame(() => {
      if (saved === "light" || saved === "dark") setTheme(saved);
    });
    const activeTimers = timers.current;
    return () => {
      window.cancelAnimationFrame(restoreTheme);
      Object.values(activeTimers).forEach(clearInterval);
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("plasma-theme", theme);
  }, [theme]);
  const now = () => new Date().toLocaleTimeString("zh-TW", { hour12: false });
  const log = (message: string) => setLogs(items => [...items.slice(-80), `${now()}  ${message}`]);

  function run(operation: "erase" | "program" | "verify" | "sequence") {
    if (!enabled || (operation !== "erase" && !firmware)) return;
    if (timers.current[selected]) clearInterval(timers.current[selected]);
    const stages: Stage[] = operation === "sequence" ? ["erase", "program", "verify"] : [operation];
    let stageIndex = 0;
    let tick = 0;
    const jobId = `WEB-${Date.now().toString(36).toUpperCase()}`;
    const apply = (stage: Stage, stageProgress: number) => {
      const overall = stages.length === 1 ? stageProgress : ((stageIndex + stageProgress / 100) / stages.length) * 100;
      setChannels(items => items.map(ch => ch.id === selected ? { ...ch, stage, stageProgress, progress: overall, jobId, file: firmware?.name } : ch));
    };
    apply(stages[0], 0);
    log(`[CH${selected}]    ${jobId} accepted · ${operation.toUpperCase()}${firmware ? ` · ${firmware.name}` : ""}`);
    log(`[CH${selected}]    ${stageLabels[stages[0]]} started`);
    timers.current[selected] = setInterval(() => {
      tick += 2;
      apply(stages[stageIndex], tick);
      if (tick >= 100) {
        log(`[CH${selected}]    ${stageLabels[stages[stageIndex]]} completed`);
        stageIndex += 1;
        tick = 0;
        if (stageIndex >= stages.length) {
          clearInterval(timers.current[selected]);
          delete timers.current[selected];
          setChannels(items => items.map(ch => ch.id === selected ? { ...ch, stage: "success", stageProgress: 100, progress: 100 } : ch));
          log(`[CH${selected}]    Job ${jobId} SUCCESS`);
        } else {
          apply(stages[stageIndex], 0);
          log(`[CH${selected}]    ${stageLabels[stages[stageIndex]]} started`);
        }
      }
    }, 110);
  }

  function cancel() {
    if (!timers.current[selected]) return;
    clearInterval(timers.current[selected]);
    delete timers.current[selected];
    setChannels(items => items.map(ch => ch.id === selected ? { ...ch, stage: "cancelled" } : ch));
    log(`[CH${selected}]    Cancel acknowledged · safe shutdown complete`);
  }

  const statusText = useMemo(() => active.stage === "idle" ? "READY" : active.stage.toUpperCase(), [active.stage]);

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brandmark">P</span><div><b>PLASMA</b><small>PROGRAMMER CONTROL</small></div></div>
        <div className="topActions">
          <div className="themeSwitch" role="group" aria-label="介面主題">
            <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} aria-pressed={theme === "dark"}>深色</button>
            <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} aria-pressed={theme === "light"}>淺色</button>
          </div>
          <div className="connection"><span className="pulse"/><div><b>PYNQ-001</b><small>192.168.1.42 · Online</small></div><span className="latency">12 ms</span></div>
        </div>
      </header>

      <div className="workspace">
        <aside>
          <p className="eyebrow">CHANNEL MATRIX</p>
          <div className="channelGrid">
            {channels.map(ch => <button key={ch.id} onClick={() => setSelected(ch.id)} className={`channel ${selected === ch.id ? "selected" : ""} ${ch.id > 1 ? "disabled" : ""}`}>
              <span>CH{ch.id}</span><i className={ch.stage}/><small>{ch.id > 1 ? "DISABLED" : stageLabels[ch.stage]}</small>
            </button>)}
          </div>
          <div className="health"><span>SYSTEM HEALTH</span><b>Nominal</b><div><i/><i/><i/><i/></div><small>CPU 24%　MEM 38%　42°C</small></div>
        </aside>

        <section className="console">
          <div className="heading"><div><p className="eyebrow">ACTIVE WORKSPACE</p><h1>Channel {selected}</h1></div><div className="headingActions"><button onClick={() => setDetailsOpen(true)}>詳細資料 ↗</button><span className={`state ${active.stage}`}>{statusText}</span></div></div>

          <div className="controlCard">
            <div className="fileDrop">
              <div className="chipIcon">⌁</div>
              <div><b>{firmware?.name ?? "選擇 Firmware 檔案"}</b><small>{firmware ? `${(firmware.size / 1024).toFixed(1)} KB · BIN` : "支援 .bin / .hex · Max 16 MB"}</small></div>
              <label>瀏覽檔案<input aria-label="選擇 Firmware 檔案" type="file" accept=".bin,.hex" onChange={e => setFirmware(e.target.files?.[0] ?? null)}/></label>
            </div>
            {!enabled && <div className="warning">CH{selected} 尚未在 Prototype 設定中啟用</div>}
            <div className="actions">
              <button onClick={() => run("erase")} disabled={!enabled || isRunning}><span>01</span>擦除<small>ERASE</small></button>
              <button onClick={() => run("program")} disabled={!enabled || !firmware || isRunning}><span>02</span>燒錄<small>PROGRAM</small></button>
              <button onClick={() => run("verify")} disabled={!enabled || !firmware || isRunning}><span>03</span>驗證<small>VERIFY</small></button>
              <button className="sequence" onClick={() => run("sequence")} disabled={!enabled || !firmware || isRunning}>執行完整流程 <b>→</b></button>
            </div>
          </div>

          <div className="progressCard">
            <div className="progressHead"><div><span className="ring">{Math.round(active.progress)}</span><div><b>{stageLabels[active.stage]}</b><small>{active.jobId ?? "尚未建立 Job"}</small></div></div><button className="cancel" onClick={cancel} disabled={!(["erase", "program", "verify"] as Stage[]).includes(active.stage)}>■　取消工作</button></div>
            <div className="track"><i style={{ width: `${active.progress}%` }}/></div>
            <div className="metrics"><span>整體進度 <b>{active.progress.toFixed(1)}%</b></span><span>階段進度 <b>{active.stageProgress.toFixed(1)}%</b></span><span>Firmware <b>{active.file ?? "—"}</b></span></div>
          </div>

          <div className="logCard">
            <div className="logHead"><div><span/>LIVE JOB LOG</div><button onClick={() => setLogs([])}>清除</button></div>
            <pre>{logs.length ? logs.join("\n") : "Log cleared."}</pre>
          </div>
        </section>
      </div>
      {detailsOpen && <div className="modalBackdrop" onClick={() => setDetailsOpen(false)}><section className="details" onClick={e => e.stopPropagation()}>
        <div className="detailsHead"><div><p className="eyebrow">JOB INSPECTOR</p><h2>Channel {selected} 詳細資料</h2></div><button aria-label="關閉詳細資料" onClick={() => setDetailsOpen(false)}>×</button></div>
        <dl><div><dt>Programmer</dt><dd>PYNQ-001</dd></div><div><dt>Job ID</dt><dd>{active.jobId ?? "—"}</dd></div><div><dt>Operation state</dt><dd>{active.stage.toUpperCase()}</dd></div><div><dt>Firmware</dt><dd>{active.file ?? "—"}</dd></div><div><dt>Protocol</dt><dd>Plasma v3.1 TCP</dd></div><div><dt>Target</dt><dd>STM32F103C8T6 (Mock)</dd></div></dl>
        <p>Prototype 的詳細檢視與主操作面板分離。未來可在此加入 checksum、開始／結束時間、錯誤堆疊與完整 Job JSON。</p>
      </section></div>}
    </main>
  );
}
