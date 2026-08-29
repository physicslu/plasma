"use client";

import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import {
  DiagnosticsTestCard,
  DiagnosticsTestNotice,
  DiagnosticsTestPage,
} from "./diagnostics-test-page";
import "./diagnostics-test-page.css";
import "./loopback-test.css";

type LoopbackEndpoint = "ps" | "pl" | "ic";
type LengthMode = "single" | "boundary" | "range";
type Pattern = "prbs" | "increment" | "zero" | "ones" | "aa" | "55" | "walking1" | "walking0";

const endpointIndex: Record<LoopbackEndpoint, number> = { ps: 1, pl: 2, ic: 3 };
const endpointLabel: Record<LoopbackEndpoint, string> = { ps: "PS", pl: "PL", ic: "IC" };
const patternLabels: Record<Pattern, string> = {
  prbs: "PRBS (Pseudo Random Binary Sequence)",
  increment: "Incrementing byte (00, 01, 02 … FF)",
  zero: "0x00",
  ones: "0xFF",
  aa: "0xAA",
  "55": "0x55",
  walking1: "Walking 1",
  walking0: "Walking 0",
};

const copy = {
  "zh-TW": {
    eyebrow: "EMODE / DIAGNOSTICS / LOOPBACK TEST",
    title: "Loopback Test",
    description: "Real-path loopback 測試，用來驗證 Web → PS → PL → IC 各層資料路徑完整性。",
    help: "說明",
    pathTitle: "Loopback Path",
    pathDescription: "選擇本次要測到的最遠節點；前級節點會自動包含在測試路徑中。",
    currentSelection: "目前選擇",
    loopbackAt: "Loopback at",
    effectivePath: "Effective Path",
    dataTitle: "Test Data Configuration",
    pattern: "Pattern",
    seed: "Seed (Hex)",
    seedHint: "僅 PRBS pattern 使用；固定 seed 讓測試可以完全重現。",
    transformPrefix: "回傳資料使用 deterministic transform，以確認資料真的抵達所選 endpoint。",
    payloadTitle: "Payload Length Configuration",
    mode: "Mode",
    single: "Single Length",
    boundary: "Boundary Test",
    range: "Range Test",
    length: "Length",
    boundaryN: "Boundary (N)",
    start: "Start",
    end: "End",
    step: "Step",
    bytes: "bytes",
    boundaryHint: "系統執行 N-1、N、N+1。",
    actualLengths: "Actual test lengths",
    executionTitle: "Test Execution Settings",
    repeat: "Repeat Count",
    repeatHint: "每個 test length 的執行次數",
    timeout: "Timeout",
    timeoutHint: "每個 test case 的 timeout",
    delay: "Inter-Packet Delay",
    delayHint: "封包之間的延遲",
    startTest: "Start Test",
    reset: "Reset",
    backendPending: "V1 先建立 Diagnostics UI 與測試參數 contract；real-path execution API 尚未接入，因此不產生假的 PASS / FAIL 結果。",
    resultsTitle: "Test Results",
    noResults: "尚未執行 real-path test。",
    resultLength: "Length (bytes)",
    resultPattern: "Pattern",
    resultSeed: "Seed (Hex)",
    txCrc: "TX CRC32",
    rxCrc: "RX CRC32",
    rtt: "RTT (ms)",
    result: "Result",
    details: "Details",
    helpText: "節點實心表示包含在本次測試路徑；空心表示不包含。選 IC 時，WEB、PS、PL、IC 會全部實心。底層 relay / routing 狀態由系統自動推導，不在此 UI 顯示。",
  },
  "en-US": {
    eyebrow: "EMODE / DIAGNOSTICS / LOOPBACK TEST",
    title: "Loopback Test",
    description: "Real-path loopback test for Web → PS → PL → IC data-path integrity.",
    help: "Help",
    pathTitle: "Loopback Path",
    pathDescription: "Select the farthest node to test. All previous nodes are included automatically.",
    currentSelection: "Current Selection",
    loopbackAt: "Loopback at",
    effectivePath: "Effective Path",
    dataTitle: "Test Data Configuration",
    pattern: "Pattern",
    seed: "Seed (Hex)",
    seedHint: "Used by PRBS only. A fixed seed keeps every test reproducible.",
    transformPrefix: "Returned data uses a deterministic transform to prove the selected endpoint handled the request.",
    payloadTitle: "Payload Length Configuration",
    mode: "Mode",
    single: "Single Length",
    boundary: "Boundary Test",
    range: "Range Test",
    length: "Length",
    boundaryN: "Boundary (N)",
    start: "Start",
    end: "End",
    step: "Step",
    bytes: "bytes",
    boundaryHint: "The system executes N-1, N and N+1.",
    actualLengths: "Actual test lengths",
    executionTitle: "Test Execution Settings",
    repeat: "Repeat Count",
    repeatHint: "Number of repeats for each test length",
    timeout: "Timeout",
    timeoutHint: "Timeout for each test case",
    delay: "Inter-Packet Delay",
    delayHint: "Delay between packets",
    startTest: "Start Test",
    reset: "Reset",
    backendPending: "V1 establishes the Diagnostics UI and test-parameter contract. The real-path execution API is not connected yet, so the UI does not fabricate PASS / FAIL results.",
    resultsTitle: "Test Results",
    noResults: "No real-path test has been executed yet.",
    resultLength: "Length (bytes)",
    resultPattern: "Pattern",
    resultSeed: "Seed (Hex)",
    txCrc: "TX CRC32",
    rxCrc: "RX CRC32",
    rtt: "RTT (ms)",
    result: "Result",
    details: "Details",
    helpText: "A filled node is included in the test path; an empty node is excluded. Selecting IC fills WEB, PS, PL and IC. Low-level relay / routing state is derived by the system and is intentionally hidden from this UI.",
  },
} as const;

function positiveInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export default function LoopbackTest() {
  const { locale } = useI18n();
  const text = copy[locale];
  const [endpoint, setEndpoint] = useState<LoopbackEndpoint>("pl");
  const [pattern, setPattern] = useState<Pattern>("prbs");
  const [seed, setSeed] = useState("0x12345678");
  const [lengthMode, setLengthMode] = useState<LengthMode>("boundary");
  const [singleLength, setSingleLength] = useState("1024");
  const [boundary, setBoundary] = useState("1024");
  const [rangeStart, setRangeStart] = useState("64");
  const [rangeEnd, setRangeEnd] = useState("4096");
  const [rangeStep, setRangeStep] = useState("64");
  const [repeatCount, setRepeatCount] = useState("1");
  const [timeoutMs, setTimeoutMs] = useState("5000");
  const [packetDelayMs, setPacketDelayMs] = useState("10");
  const [helpOpen, setHelpOpen] = useState(false);

  const selectedIndex = endpointIndex[endpoint];
  const effectivePath = endpoint === "ps"
    ? "Web → PS → Web"
    : endpoint === "pl"
      ? "Web → PS → PL → PS → Web"
      : "Web → PS → PL → IC → PL → PS → Web";

  const transformText = endpoint === "ps"
    ? "PS: RX[i] = TX[i]"
    : endpoint === "pl"
      ? "PL: RX[i] = TX[i] XOR 0x55"
      : "IC: RX[i] = TX[i] XOR 0xFF";

  const actualLengths = useMemo(() => {
    if (lengthMode === "single") return [positiveInteger(singleLength, 1)];
    if (lengthMode === "boundary") {
      const n = positiveInteger(boundary, 1);
      return [Math.max(1, n - 1), n, n + 1];
    }
    const start = positiveInteger(rangeStart, 1);
    const end = Math.max(start, positiveInteger(rangeEnd, start));
    const step = positiveInteger(rangeStep, 1);
    const values: number[] = [];
    for (let value = start; value <= end && values.length < 6; value += step) values.push(value);
    return values;
  }, [boundary, lengthMode, rangeEnd, rangeStart, rangeStep, singleLength]);

  const rangeHasMore = lengthMode === "range"
    && actualLengths.length === 6
    && actualLengths[actualLengths.length - 1] + positiveInteger(rangeStep, 1) <= positiveInteger(rangeEnd, 1);

  function reset() {
    setEndpoint("pl");
    setPattern("prbs");
    setSeed("0x12345678");
    setLengthMode("boundary");
    setSingleLength("1024");
    setBoundary("1024");
    setRangeStart("64");
    setRangeEnd("4096");
    setRangeStep("64");
    setRepeatCount("1");
    setTimeoutMs("5000");
    setPacketDelayMs("10");
  }

  return (
    <DiagnosticsTestPage
      eyebrow={text.eyebrow}
      title={text.title}
      description={text.description}
      help={(
        <button type="button" aria-expanded={helpOpen} onClick={() => setHelpOpen(value => !value)}>
          ? {text.help}
        </button>
      )}
    >
      {helpOpen && <DiagnosticsTestNotice>{text.helpText}</DiagnosticsTestNotice>}

      <DiagnosticsTestCard title={text.pathTitle} description={text.pathDescription} className="loopbackPathCard">
        <div className="loopbackPath" aria-label="Web to IC loopback path">
          {(["WEB", "PS", "PL", "IC"] as const).map((label, index) => (
            <div className="loopbackPathItem" key={label}>
              <span className="loopbackNodeLabel">{label}</span>
              <div className="loopbackNodeRow">
                {index > 0 && <span className={`loopbackSegment ${index <= selectedIndex ? "active" : ""}`} aria-hidden="true" />}
                {label === "WEB" ? (
                  <span className="loopbackNode active" aria-label="WEB included" />
                ) : (
                  <button
                    type="button"
                    className={`loopbackNode ${index <= selectedIndex ? "active" : ""}`}
                    aria-label={`${label} loopback endpoint`}
                    aria-pressed={index === selectedIndex}
                    onClick={() => setEndpoint(label.toLowerCase() as LoopbackEndpoint)}
                  />
                )}
              </div>
              <small>{label === "WEB" ? "Web Console" : label === "PS" ? "Processing System" : label === "PL" ? "Programmable Logic" : "Diagnostic FW"}</small>
            </div>
          ))}
        </div>

        <DiagnosticsTestNotice>
          <strong>{text.currentSelection}: {endpointLabel[endpoint]} ({text.loopbackAt} {endpointLabel[endpoint]})</strong>
          <span>{text.effectivePath}: {effectivePath}</span>
        </DiagnosticsTestNotice>
      </DiagnosticsTestCard>

      <div className="loopbackConfigGrid">
        <DiagnosticsTestCard title={text.dataTitle}>
          <div className="diagnosticsFieldStack">
            <label className="diagnosticsField">
              <span>{text.pattern}</span>
              <select value={pattern} onChange={event => setPattern(event.target.value as Pattern)}>
                {(Object.keys(patternLabels) as Pattern[]).map(value => (
                  <option key={value} value={value}>{patternLabels[value]}</option>
                ))}
              </select>
            </label>
            <label className="diagnosticsField">
              <span>{text.seed}</span>
              <input
                value={seed}
                disabled={pattern !== "prbs"}
                spellCheck={false}
                onChange={event => setSeed(event.target.value)}
              />
              <small>{text.seedHint}</small>
            </label>
          </div>
          <DiagnosticsTestNotice>
            <span>{text.transformPrefix}</span>
            <strong>{transformText}</strong>
          </DiagnosticsTestNotice>
        </DiagnosticsTestCard>

        <DiagnosticsTestCard title={text.payloadTitle}>
          <div className="loopbackLengthModes" role="group" aria-label={text.mode}>
            {(["single", "boundary", "range"] as LengthMode[]).map(mode => (
              <button
                key={mode}
                type="button"
                className={lengthMode === mode ? "active" : ""}
                aria-pressed={lengthMode === mode}
                onClick={() => setLengthMode(mode)}
              >
                <span aria-hidden="true">{lengthMode === mode ? "●" : "○"}</span>
                {mode === "single" ? text.single : mode === "boundary" ? text.boundary : text.range}
              </button>
            ))}
          </div>

          {lengthMode === "single" && (
            <label className="diagnosticsField diagnosticsNumberField">
              <span>{text.length}</span>
              <div><input type="number" min="1" value={singleLength} onChange={event => setSingleLength(event.target.value)} /><em>{text.bytes}</em></div>
            </label>
          )}

          {lengthMode === "boundary" && (
            <label className="diagnosticsField diagnosticsNumberField">
              <span>{text.boundaryN}</span>
              <div><input type="number" min="1" value={boundary} onChange={event => setBoundary(event.target.value)} /><em>{text.bytes}</em></div>
              <small>{text.boundaryHint}</small>
            </label>
          )}

          {lengthMode === "range" && (
            <div className="loopbackRangeFields">
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.start}</span>
                <div><input type="number" min="1" value={rangeStart} onChange={event => setRangeStart(event.target.value)} /><em>{text.bytes}</em></div>
              </label>
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.end}</span>
                <div><input type="number" min="1" value={rangeEnd} onChange={event => setRangeEnd(event.target.value)} /><em>{text.bytes}</em></div>
              </label>
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.step}</span>
                <div><input type="number" min="1" value={rangeStep} onChange={event => setRangeStep(event.target.value)} /><em>{text.bytes}</em></div>
              </label>
            </div>
          )}

          <DiagnosticsTestNotice>
            <strong>{text.actualLengths}:</strong>
            <span>{actualLengths.map(value => `${value} ${text.bytes}`).join(", ")}{rangeHasMore ? " …" : ""}</span>
          </DiagnosticsTestNotice>
        </DiagnosticsTestCard>
      </div>

      <DiagnosticsTestCard title={text.executionTitle}>
        <div className="loopbackExecutionGrid">
          <label className="diagnosticsField diagnosticsNumberField">
            <span>{text.repeat}</span>
            <div><input type="number" min="1" value={repeatCount} onChange={event => setRepeatCount(event.target.value)} /></div>
            <small>{text.repeatHint}</small>
          </label>
          <label className="diagnosticsField diagnosticsNumberField">
            <span>{text.timeout}</span>
            <div><input type="number" min="1" value={timeoutMs} onChange={event => setTimeoutMs(event.target.value)} /><em>ms</em></div>
            <small>{text.timeoutHint}</small>
          </label>
          <label className="diagnosticsField diagnosticsNumberField">
            <span>{text.delay}</span>
            <div><input type="number" min="0" value={packetDelayMs} onChange={event => setPacketDelayMs(event.target.value)} /><em>ms</em></div>
            <small>{text.delayHint}</small>
          </label>
          <div className="loopbackExecutionActions">
            <button type="button" className="primary" disabled title={text.backendPending}>▷ {text.startTest}</button>
            <button type="button" onClick={reset}>↻ {text.reset}</button>
          </div>
        </div>
        <p className="loopbackBackendBoundary">{text.backendPending}</p>
      </DiagnosticsTestCard>

      <DiagnosticsTestCard title={text.resultsTitle} className="loopbackResultsCard">
        <div className="loopbackResultsWrap">
          <table>
            <thead>
              <tr>
                <th>{text.resultLength}</th>
                <th>{text.resultPattern}</th>
                <th>{text.resultSeed}</th>
                <th>{text.txCrc}</th>
                <th>{text.rxCrc}</th>
                <th>{text.rtt}</th>
                <th>{text.result}</th>
                <th>{text.details}</th>
              </tr>
            </thead>
          </table>
          <div className="loopbackEmptyResults">
            <span aria-hidden="true">▱</span>
            <p>{text.noResults}</p>
          </div>
        </div>
      </DiagnosticsTestCard>
    </DiagnosticsTestPage>
  );
}
