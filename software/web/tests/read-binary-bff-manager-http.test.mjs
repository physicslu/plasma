// Host-only integration: Console BFF -> real Manager HTTP server -> READ binary.
//
// Root cause (SWPC, 2026-11-11): the Manager emitted `Content-Length` twice for
// the Read Memory binary. Node.js fetch rejects that response
// (HPE_UNEXPECTED_CONTENT_LENGTH), so the BFF answered
// `503 manager_unavailable` for a PASS Read. This test drives the real BFF
// module with real Node.js fetch against the real Python Manager handler.
// It is not HIL evidence.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFile, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import test, { after, before } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const bffDir = new URL("../app/api/manager/", import.meta.url);
const fixture = fileURLToPath(new URL("./fixtures/manager-read-output-server.py", import.meta.url));
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

let relay;
let manager;
let facts;
let workDir;

async function loadBff() {
  // The BFF is TypeScript inside the Next.js app; transpile it as-is so the
  // test runs the shipped relay logic on the Node.js runtime fetch.
  workDir = await mkdtemp(join(tmpdir(), "plasma-bff-"));
  for (const name of ["bootstrap-bff", "manager-bff"]) {
    const source = await readFile(new URL(`${name}.ts`, bffDir), "utf8");
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    });
    await writeFile(join(workDir, `${name}.mjs`),
      outputText.replace('"./manager-bff"', '"./manager-bff.mjs"'));
  }
  await copyFile(new URL("maintenance-capability.mjs", bffDir),
    join(workDir, "maintenance-capability.mjs"));
  return (await import(pathToFileURL(join(workDir, "bootstrap-bff.mjs")).href))
    .relayManagerBootstrapRequest;
}

function useManager(port) {
  process.env.PLASMA_CONTROL_STATION_MODE = "managed";
  process.env.PLASMA_MANAGER_API_URL = `http://127.0.0.1:${port}`;
}

function download(runId) {
  return relay(new Request(`http://console.local/api/manager/registry/z2/bootstrap/programming/runs/${runId}/output`),
    "z2", `programming/runs/${runId}/output`);
}

// A raw upstream that answers every request with fixed bytes.
async function rawUpstream(responseBytes) {
  const server = createServer(socket => {
    socket.once("data", () => socket.end(responseBytes));
    socket.on("error", () => {});
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  return { port: server.address().port, close: () => new Promise(resolve => server.close(resolve)) };
}

before(async () => {
  relay = await loadBff();
  manager = spawn(process.env.PYTHON ?? "python3", [fixture], { stdio: ["pipe", "pipe", "inherit"] });
  const lines = createInterface({ input: manager.stdout });
  facts = JSON.parse(await new Promise((resolve, reject) => {
    lines.once("line", resolve);
    manager.once("exit", code => reject(new Error(`Manager fixture exited early: ${code}`)));
    manager.once("error", reject);
  }));
});

after(async () => {
  manager?.stdin.end();
  if (workDir) await rm(workDir, { recursive: true, force: true });
});

test("the real Manager sends the READ binary with exactly one Content-Length", async () => {
  // Read the raw response so a repeated header cannot be hidden by a client.
  const { connect } = await import("node:net");
  const raw = await new Promise((resolve, reject) => {
    const chunks = [];
    const socket = connect(facts.port, "127.0.0.1", () => socket.write(
      `GET /api/registry/z2/bootstrap/programming/runs/${facts.runs.ok}/output HTTP/1.1\r\n`
      + "Host: 127.0.0.1\r\nConnection: close\r\n\r\n"));
    socket.on("data", chunk => chunks.push(chunk));
    socket.on("end", () => resolve(Buffer.concat(chunks)));
    socket.on("error", reject);
  });
  const split = raw.indexOf("\r\n\r\n");
  const head = raw.subarray(0, split).toString("latin1").split("\r\n");
  const body = raw.subarray(split + 4);
  assert.match(head[0], /^HTTP\/1\.[01] 200 /);
  const lengths = head.filter(line => /^content-length:/i.test(line));
  assert.deepEqual(lengths, [`Content-Length: ${facts.bytes}`]);
  assert.equal(body.length, facts.bytes);
  assert.equal(sha256(body), facts.sha256);
});

test("Console BFF relays the READ binary from the real Manager through Node.js fetch", async () => {
  useManager(facts.port);
  // Direct Node.js fetch of the Manager must parse (no HPE_UNEXPECTED_CONTENT_LENGTH).
  const direct = await fetch(`http://127.0.0.1:${facts.port}/api/registry/z2/bootstrap/programming/runs/${facts.runs.ok}/output`);
  assert.equal(direct.status, 200);
  assert.equal((await direct.arrayBuffer()).byteLength, facts.bytes);

  const response = await download(facts.runs.ok);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Content-Type"), "application/octet-stream");
  assert.equal(response.headers.get("Content-Disposition"), `attachment; filename="${facts.filename}"`);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
  const bytes = Buffer.from(await response.arrayBuffer());
  assert.equal(bytes.length, facts.bytes);
  assert.equal(sha256(bytes), facts.sha256);
  assert.equal(response.headers.get("X-Plasma-Read-Sha256"), facts.sha256);
});

test("missing binary, SHA-256 mismatch and non-PASS runs stay fail-closed as Manager JSON", async () => {
  useManager(facts.port);
  for (const [kind, status] of [["missing", 410], ["mismatch", 410], ["failed", 409]]) {
    const response = await download(facts.runs[kind]);
    assert.equal(response.status, status, kind);
    assert.match(response.headers.get("Content-Type"), /application\/json/, kind);
    assert.equal(response.headers.get("X-Plasma-Read-Sha256"), null, kind);
    assert.equal(response.headers.get("Content-Disposition"), null, kind);
    const payload = await response.json();
    // The Manager's own verdict reaches the Browser: not manager_unavailable.
    assert.equal(payload.error.code, "read_output_unavailable", kind);
  }
  const unknown = await download("e".repeat(32));
  assert.equal(unknown.status, 404);
  assert.equal((await unknown.json()).error.code, "programming_run_not_found");
});

test("an upstream with duplicate Content-Length is refused, never relayed as a binary", async () => {
  // The exact header shape captured on SWPC before the fix.
  const body = Buffer.alloc(64, 0xa5);
  const upstream = await rawUpstream(Buffer.concat([Buffer.from(
    "HTTP/1.0 200 OK\r\n"
    + "Content-Type: application/octet-stream\r\n"
    + `Content-Length: ${body.length}\r\n`
    + 'Content-Disposition: attachment; filename="read-STM32F103C8T6-0x08000000-64.bin"\r\n'
    + `X-Plasma-Read-Sha256: ${sha256(body)}\r\n`
    + `Content-Length: ${body.length}\r\n\r\n`), body]));
  try {
    // Node.js fetch itself rejects it. The code depends on the Node.js/undici
    // version: HPE_UNEXPECTED_CONTENT_LENGTH or UND_ERR_RES_CONTENT_LENGTH_MISMATCH.
    await assert.rejects(
      fetch(`http://127.0.0.1:${upstream.port}/`),
      error => ["HPE_UNEXPECTED_CONTENT_LENGTH", "UND_ERR_RES_CONTENT_LENGTH_MISMATCH"]
        .includes(error?.cause?.code));
    useManager(upstream.port);
    const response = await download(facts.runs.ok);
    assert.equal(response.status, 503);
    assert.match(response.headers.get("Content-Type"), /application\/json/);
    assert.equal((await response.json()).error.code, "manager_unavailable");
  } finally {
    await upstream.close();
  }
});

test("a binary with an abnormal type or digest header is not passed through", async () => {
  const body = Buffer.alloc(32, 0x5a);
  const respond = headers => Buffer.concat([Buffer.from(
    `HTTP/1.1 200 OK\r\n${headers}Content-Length: ${body.length}\r\nConnection: close\r\n\r\n`), body]);
  // Not an octet-stream: refused as a non-JSON upstream, no bytes relayed.
  let upstream = await rawUpstream(respond("Content-Type: text/html\r\n"));
  try {
    useManager(upstream.port);
    const response = await download(facts.runs.ok);
    assert.equal(response.status, 502);
    assert.equal((await response.json()).error.code, "bootstrap_upstream_non_json");
  } finally {
    await upstream.close();
  }
  // Malformed digest / disposition headers are dropped, never forwarded.
  upstream = await rawUpstream(respond(
    "Content-Type: application/octet-stream\r\n"
    + "X-Plasma-Read-Sha256: not-a-digest\r\n"
    + 'Content-Disposition: attachment; filename="../../etc/passwd"\r\n'));
  try {
    useManager(upstream.port);
    const response = await download(facts.runs.ok);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("X-Plasma-Read-Sha256"), null);
    assert.equal(response.headers.get("Content-Disposition"), 'attachment; filename="read-memory.bin"');
  } finally {
    await upstream.close();
  }
});

test("the READ binary path adds no retry and no second Content-Length producer", async () => {
  const [bff, handler, server] = await Promise.all([
    readFile(new URL("bootstrap-bff.ts", bffDir), "utf8"),
    readFile(new URL("../../python/plasma_manager/bootstrap_server.py", import.meta.url), "utf8"),
    readFile(new URL("../../python/plasma_manager/server.py", import.meta.url), "utf8"),
  ]);
  assert.equal(bff.match(/\bfetch\(/g).length, 1);
  assert.doesNotMatch(bff, /\bfor\s*\(|\bwhile\s*\(|attempt/i);
  assert.doesNotMatch(handler, /["']Content-Length["']/);
  assert.match(server, /def _raw_response[\s\S]*?send_header\("Content-Length", str\(len\(body\)\)\)/);
});
