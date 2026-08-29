"use client";

import { useMemo, useState } from "react";
import { PlasmaApiError } from "../plasma-api";
import { useWorkspaceSession } from "../workspace-session";
import { useI18n } from "../i18n";
import {
  executePsLoopbackCase,
  type LoopbackEndpoint,
  type LoopbackPattern,
} from "./diagnostics-api";
import {
  DiagnosticsTestCard,
  DiagnosticsTestNotice,
  DiagnosticsTestPage,
} from "./diagnostics-test-page";
import "./diagnostics-test-page.css";
import "./loopback-test.css";
import "./loopback-test-results.css";

type LengthMode = "single" | "boundary" | "range";
type LoopbackResultStatus = "PASS" | "FAIL" | "TIMEOUT" | "ERROR";
type LoopbackResultRow = {
  id: string;
  length: number;
  pattern: LoopbackPattern;
  seed: string;
  txCrc32: string;
  rxCrc32: string;
  rttMs: number | null;
  status: LoopbackResultStatus;
  details: string;
};

const endpointIndex: Record<LoopbackEndpoint, number> = { ps: 1, pl: 2, ic: 3 };
const endpointLabel: Record<LoopbackEndpoint, string> = { ps: "PS", pl: "PL", ic: "IC" };
const patternLabels: Record<LoopbackPattern, string> = {
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
    description: "Production real-path loopback 測試，用來驗證 Web 經 Plasma Manager 到 PPU 後的 PS → PL → IC 各層資料路徑完整性。",
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
    transformPrefix: "Response contract 由所選 endpoint 決定；只有真正抵達該 endpoint 才能 PASS。",
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
    psReady: "PS production real-path 已透過 Manager Phase 0 pass-through 啟用：Browser → Web BFF → Plasma Manager → PPU REST Gateway → Plasma Server → Browser。此路徑不使用 MockInterface，也不會 fallback 到 Mock。",
    laterEndpoint: "PL / IC real-path 尚未實作；選擇這些 endpoint 時 Start Test 會保持停用，不會產生假的 PASS / FAIL。",
    running: "Production real-path test 執行中",
    resultsTitle: "Test Results",
    noResults: "尚未執行 production real-path test。",
    resultLength: "Length (bytes)",
    resultPattern: "Pattern",
    resultSeed: "Seed (Hex)",
    txCrc: "TX CRC32",
    rxCrc: "RX CRC32",
    rtt: "RTT (ms)",
    result: "Result",
    details: "Details",
    helpText: "節點實心表示包含在本次測試路徑；空心表示不包含。目前只有 PS endpoint 可執行。PS PASS 必須是 Browser payload 實際穿過 Web BFF、Plasma Manager、PPU REST Gateway 與 Plasma Protocol v3.3 TCP 連線，由 Plasma Server PS handler 回傳；Browser 還會獨立驗證 Manager pass-through proof、PS source、Test ID、sequence、payload 與 CRC。",
  },
  "en-US": {
    eyebrow: "EMODE / DIAGNOSTICS / LOOPBACK TEST",
    title: "Loopback Test",
    description: "Production real-path loopback test for the Web-through-Manager path into PPU PS → PL → IC data-path integrity.",
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
    transformPrefix: "The selected endpoint defines the response contract. PASS requires proof that the endpoint actually handled the payload.",
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
    psReady: "The PS production real path now uses the Manager Phase 0 pass-through: Browser → Web BFF → Plasma Manager → PPU REST Gateway → Plasma Server → Browser. This path does not use MockInterface and never falls back to Mock.",
    laterEndpoint: "PL / IC real-path execution is not implemented yet. Start Test stays disabled for those endpoints and no synthetic PASS / FAIL is produced.",
    running: "Production real-path test is running",
    resultsTitle: "Test Results",
    noResults: "No production real-path test has been executed yet.",
    resultLength: "Length (bytes)",
    resultPattern: "Pattern",
    resultSeed: "Seed (Hex)",
    txCrc: "TX CRC32",
    rxCrc: "RX CRC32",
    rtt: "RTT (ms)",
    result: "Result",
    details: "Details",
    helpText: "A filled node is included in the test path; an empty node is excluded. Only the PS endpoint executes today. A PS PASS requires the Browser payload to traverse the Web BFF, Plasma Manager, PPU REST Gateway and Plasma Protocol v3.3 TCP connection, be returned by the Plasma Server PS handler, and then pass independent Browser verification of the Manager relay proof, PS source, Test ID, sequence, payload and CRC.",
  },
} as const;

function positiveInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function nonnegativeInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function parseSeed(value: string): number | null {
  const normalized = value.trim().replace(/^0x/i, "");
  if (!/^[0-9a-f]{1,8}$/i.test(normalized)) return null;
  return Number.parseInt(normalized, 16) >>> 0;
}

function generatePayload(pattern: LoopbackPattern, length: number, seed: number): Uint8Array {
  const payload = new Uint8Array(length);
  let state = seed >>> 0;
  for (let index = 0; index < length; index += 1) {
    switch (pattern) {
      case "zero": payload[index] = 0x00; break;
      case "ones": payload[index] = 0xff; break;
      case "aa": payload[index] = 0xaa; break;
      case "55": payload[index] = 0x55; break;
      case "increment": payload[index] = index & 0xff; break;
      case "walking1": payload[index] = 1 << (index % 8); break;
      case "walking0": payload[index] = (~(1 << (index % 8))) & 0xff; break;
      case "prbs": {
        state ^= state << 13;
        state ^= state >>> 17;
        state ^= state << 5;
        state >>>= 0;
        payload[index] = state & 0xff;
        break;
      }
    }
  }
  return payload;
}

const crcTable = (() => {
  const table = new Uint32Array(256);
  for (let value = 0; value < 256; value += 1) {
    let crc = value;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc & 1) ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    table[value] = crc >>> 0;
  }
  return table;
})();

function crc32Hex(payload: Uint8Array): string {
  let crc = 0xffffffff;
  for (const value of payload) crc = crcTable[(crc ^ value) & 0xff] ^ (crc >>> 8);
  return ((crc ^ 0xffffffff) >>> 0).toString(16).padStart(8, "0");
}

function bytesToBase64(payload: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < payload.length; offset += chunkSize) {
    binary += String.fromCharCode(...payload.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = window.atob(value);
  const payload = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) payload[index] = binary.charCodeAt(index);
  return payload;
}

function firstMismatch(expected: Uint8Array, actual: Uint8Array): number | null {
  const limit = Math.min(expected.length, actual.length);
  for (let index = 0; index < limit; index += 1) {
    if (expected[index] !== actual[index]) return index;
  }
  return expected.length === actual.length ? null : limit;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

export default function LoopbackTest() {
  const { locale } = useI18n();
  const { apiBase } = useWorkspaceSession();
  const text = copy[locale];
  const [endpoint, setEndpoint] = useState<LoopbackEndpoint>("pl");
  const [pattern, setPattern] = useState<LoopbackPattern>("prbs");
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
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<LoopbackResultRow[]>([]);
  const [runError, setRunError] = useState<string | null>(null);

  const selectedIndex = endpointIndex[endpoint];
  const effectivePath = endpoint === "ps"
    ? "Web → PS → Web"
    : endpoint === "pl"
      ? "Web → PS → PL → PS → Web"
      : "Web → PS → PL → IC → PL → PS → Web";

  const transformText = endpoint === "ps"
    ? "PS: RX[i] = TX[i] (echo)"
    : endpoint === "pl"
      ? "PL: NOT_READY — real-path execution is not implemented"
      : "IC: NOT_READY — real-path execution is not implemented";

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
    if (running) return;
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
    setResults([]);
    setRunError(null);
  }

  async function runPsLoopback(): Promise<void> {
    if (running || endpoint !== "ps") return;
    const parsedSeed = parseSeed(seed);
    if (pattern === "prbs" && parsedSeed === null) {
      setRunError("PRBS seed must be 1..8 hexadecimal digits, optionally prefixed with 0x.");
      return;
    }
    const effectiveSeed = parsedSeed ?? 0;
    const repeats = positiveInteger(repeatCount, 1);
    const timeout = positiveInteger(timeoutMs, 5000);
    const delay = nonnegativeInteger(packetDelayMs, 0);
    const testId = window.crypto.randomUUID();
    let sequence = 0;
    const rows: LoopbackResultRow[] = [];
    setRunError(null);
    setResults([]);
    setRunning(true);

    try {
      for (const length of actualLengths) {
        for (let repeat = 0; repeat < repeats; repeat += 1) {
          const payload = generatePayload(pattern, length, effectiveSeed);
          const txCrc32 = crc32Hex(payload);
          const rowId = `${testId}-${sequence}`;
          const startedAt = performance.now();
          try {
            const response = await executePsLoopbackCase(apiBase, {
              endpoint: "ps",
              test_id: testId,
              sequence,
              pattern,
              seed: pattern === "prbs" ? seed : "",
              payload_length: payload.length,
              payload_base64: bytesToBase64(payload),
              tx_crc32: txCrc32,
              timeout_ms: timeout,
            });
            const rttMs = performance.now() - startedAt;
            const returned = base64ToBytes(response.payload_base64);
            const mismatch = firstMismatch(payload, returned);
            const rxCrc32 = crc32Hex(returned);
            const metadataValid = response.loopback.endpoint === "ps"
              && response.loopback.source === "ps"
              && response.loopback.test_id === testId
              && response.loopback.sequence === sequence
              && response.loopback.transform === "echo"
              && response.loopback.payload_length === payload.length
              && response.loopback.tx_crc32 === txCrc32
              && response.loopback.rx_crc32 === rxCrc32;
            const pass = mismatch === null && metadataValid && txCrc32 === rxCrc32;
            rows.push({
              id: rowId,
              length,
              pattern,
              seed: pattern === "prbs" ? seed : "—",
              txCrc32,
              rxCrc32,
              rttMs,
              status: pass ? "PASS" : "FAIL",
              details: pass
                ? `Manager RTT ${response.manager.manager_rtt_ms.toFixed(3)} ms · PPU RTT ${response.loopback.ppu_rtt_ms.toFixed(3)} ms · sequence ${sequence}`
                : mismatch !== null
                  ? `Payload mismatch at offset ${mismatch}`
                  : "PS response metadata or CRC contract mismatch",
            });
          } catch (error) {
            const rttMs = performance.now() - startedAt;
            const timeoutFailure = error instanceof PlasmaApiError && error.errorCode === "E2002";
            rows.push({
              id: rowId,
              length,
              pattern,
              seed: pattern === "prbs" ? seed : "—",
              txCrc32,
              rxCrc32: "—",
              rttMs,
              status: timeoutFailure ? "TIMEOUT" : "ERROR",
              details: error instanceof Error ? error.message : String(error),
            });
          }
          setResults([...rows]);
          sequence += 1;
          if (delay > 0) await sleep(delay);
        }
      }
    } finally {
      setRunning(false);
    }
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
              <select value={pattern} onChange={event => setPattern(event.target.value as LoopbackPattern)} disabled={running}>
                {(Object.keys(patternLabels) as LoopbackPattern[]).map(value => (
                  <option key={value} value={value}>{patternLabels[value]}</option>
                ))}
              </select>
            </label>
            <label className="diagnosticsField">
              <span>{text.seed}</span>
              <input
                value={seed}
                disabled={pattern !== "prbs" || running}
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
                disabled={running}
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
              <div><input type="number" min="1" value={singleLength} disabled={running} onChange={event => setSingleLength(event.target.value)} /><em>{text.bytes}</em></div>
            </label>
          )}

          {lengthMode === "boundary" && (
            <label className="diagnosticsField diagnosticsNumberField">
              <span>{text.boundaryN}</span>
              <div><input type="number" min="1" value={boundary} disabled={running} onChange={event => setBoundary(event.target.value)} /><em>{text.bytes}</em></div>
              <small>{text.boundaryHint}</small>
            </label>
          )}

          {lengthMode === "range" && (
            <div className="loopbackRangeFields">
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.start}</span>
                <div><input type="number" min="1" value={rangeStart} disabled={running} onChange={event => setRangeStart(event.target.value)} /><em>{text.bytes}</em></div>
              </label>
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.end}</span>
                <div><input type="number" min="1" value={rangeEnd} disabled={running} onChange={event => setRangeEnd(event.target.value)} /><em>{text.bytes}</em></div>
              </label>
              <label className="diagnosticsField diagnosticsNumberField">
                <span>{text.step}</span>
                <div><input type="number" min="1" value={rangeStep} disabled={running} onChange={event => setRangeStep(event.target.value)} /><em>{text.bytes}</em></div>
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
            <div><input type="number" min="1" value={repeatCount} disabled={running} onChange={event => setRepeatCount(event.target.value)} /></div>
            <small>{text.repeatHint}</small>
          </label>
          <label className="diagnosticsField diagnosticsNumberField">
            <span>{text.timeout}</span>
            <div><input type="number" min="100" value={timeoutMs} disabled={running} onChange={event => setTimeoutMs(event.target.value)} /><em>ms</em></div>
            <small>{text.timeoutHint}</small>
          </label>
          <label className="diagnosticsField diagnosticsNumberField">
            <span>{text.delay}</span>
            <div><input type="number" min="0" value={packetDelayMs} disabled={running} onChange={event => setPacketDelayMs(event.target.value)} /><em>ms</em></div>
            <small>{text.delayHint}</small>
          </label>
          <div className="loopbackExecutionActions">
            <button
              type="button"
              className="primary"
              disabled={running || endpoint !== "ps"}
              title={endpoint === "ps" ? text.psReady : text.laterEndpoint}
              onClick={() => void runPsLoopback()}
            >
              ▷ {running ? text.running : text.startTest}
            </button>
            <button type="button" disabled={running} onClick={reset}>↻ {text.reset}</button>
          </div>
        </div>
        <p className="loopbackBackendBoundary">{text.psReady}</p>
        {endpoint !== "ps" && <p className="loopbackBackendBoundary">{text.laterEndpoint}</p>}
        {running && <p className="loopbackExecutionState"><strong>{text.running}</strong> · {results.length} case(s) completed</p>}
        {runError && <p className="loopbackExecutionState loopbackCaseError">{runError}</p>}
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
            {results.length > 0 && (
              <tbody>
                {results.map(row => (
                  <tr key={row.id}>
                    <td>{row.length}</td>
                    <td>{patternLabels[row.pattern]}</td>
                    <td>{row.seed}</td>
                    <td>{row.txCrc32}</td>
                    <td>{row.rxCrc32}</td>
                    <td>{row.rttMs === null ? "—" : row.rttMs.toFixed(3)}</td>
                    <td><span className={`loopbackResultBadge ${row.status.toLowerCase()}`}>{row.status}</span></td>
                    <td className={row.status === "PASS" ? "" : "loopbackCaseError"}>{row.details}</td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>
          {results.length === 0 && (
            <div className="loopbackEmptyResults">
              <span aria-hidden="true">▱</span>
              <p>{text.noResults}</p>
            </div>
          )}
        </div>
      </DiagnosticsTestCard>
    </DiagnosticsTestPage>
  );
}
