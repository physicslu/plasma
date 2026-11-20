"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import ThemeSwitch from "../theme-switch";
import { useWorkspaceSession } from "../workspace-session";
import "./style.css";

type LocalEntry = {
  record: { vendor: string; identifier: string; family: string; package: string; flash_size: string };
  profile: Record<string, unknown>;
  revision?: number;
  change?: string;
};
type History = { active_revision: string | null; revisions: Array<{ revision: string; count: number }>; audit: Array<{ action: string; actor: string; revision: string; detail: string; created_at: string }> };
type OfficialEntry = { record: Record<string, unknown>; qualification: Record<string, unknown>; revision: string };
type Evidence = { evidence_id: string; authority: string; reference: string; source_revision: string; acquired_at: string };
type DiffEntry = { vendor: string; identifier: string; status: string; before?: { record: Record<string, unknown>; qualification: Record<string, unknown> }; after?: { record: Record<string, unknown>; qualification: Record<string, unknown> } };
type OfficialSummary = { vendor: string; identifier: string; family: string; source: string; level: number };
type CatalogIdentityCollision = {
  manufacturer: string;
  exact_icpn: string;
  local_revision: number | null;
  local_profile_id: string | null;
};
type CatalogApiErrorBody = {
  code?: string; message?: string; conflicts?: CatalogIdentityCollision[];
  conflict_count?: number; truncated?: boolean;
};
class CatalogIdentityCollisionError extends Error {
  readonly code = "CATALOG_LOCAL_IDENTITY_CONFLICT";
  readonly conflicts: CatalogIdentityCollision[];
  readonly total: number;
  readonly truncated: boolean;
  constructor(error: CatalogApiErrorBody) {
    super(error.message ?? "Official Catalog update blocked by customer-owned part numbers");
    this.name = "CatalogIdentityCollisionError";
    this.conflicts = error.conflicts ?? [];
    this.total = error.conflict_count ?? this.conflicts.length;
    this.truncated = Boolean(error.truncated);
  }
}
const base = "/api/manager/catalog/management";
const empty: LocalEntry = { record: { vendor: "", identifier: "", family: "", package: "", flash_size: "" }, profile: { profile_id: "", provider_id: "", operations: [] } };

async function api<T>(action = "", body?: object, query = ""): Promise<T> {
  const response = await fetch(`${base}${action ? `/${action}` : ""}${query}`, {
    method: body ? "POST" : "GET", cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const result = await response.json() as T & { error?: CatalogApiErrorBody };
  if (!response.ok && response.status === 409 && result.error?.code === "CATALOG_LOCAL_IDENTITY_CONFLICT") {
    throw new CatalogIdentityCollisionError(result.error);
  }
  if (!response.ok) throw new Error(result.error?.message ?? `Catalog HTTP ${response.status}`);
  return result;
}

function parseCsv(text: string): LocalEntry[] {
  const lines = text.trim().split(/\r?\n/);
  const cells = (line: string) => {
    const values: string[] = []; let value = ""; let quoted = false;
    for (let i = 0; i < line.length; i++) {
      if (line[i] === '"' && quoted && line[i + 1] === '"') { value += '"'; i++; }
      else if (line[i] === '"') quoted = !quoted;
      else if (line[i] === "," && !quoted) { values.push(value); value = ""; }
      else value += line[i];
    }
    if (quoted) throw new Error("Unclosed CSV quote");
    values.push(value); return values;
  };
  const columns = cells(lines.shift() ?? "");
  for (const required of ["vendor", "identifier", "family", "package", "flash_size", "profile_id"]) {
    if (!columns.includes(required)) throw new Error(`CSV column ${required} is required`);
  }
  return lines.filter(Boolean).map(line => {
    const values = cells(line); if (values.length !== columns.length) throw new Error("CSV row width mismatch");
    const row = Object.fromEntries(columns.map((column, index) => [column, values[index]]));
    return { record: { vendor: row.vendor, identifier: row.identifier, family: row.family, package: row.package, flash_size: row.flash_size }, profile: { profile_id: row.profile_id, provider_id: row.provider_id ?? "", operations: row.operations ? row.operations.split("|") : [] } };
  });
}

function ManagementContent() {
  const [local, setLocal] = useState<LocalEntry[]>([]);
  const [history, setHistory] = useState<History | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [form, setForm] = useState<LocalEntry>(empty);
  const [search, setSearch] = useState("");
  const [batch, setBatch] = useState<LocalEntry[]>([]);
  const [officialBatch, setOfficialBatch] = useState<Array<{ record: Record<string, unknown>; qualification: Record<string, unknown> }>>([]);
  const [preview, setPreview] = useState<LocalEntry[]>([]);
  const [official, setOfficial] = useState<OfficialEntry | null>(null);
  const [officialVendor, setOfficialVendor] = useState("");
  const [officialICPN, setOfficialICPN] = useState("");
  const [officialSearch, setOfficialSearch] = useState("");
  const [officialMatches, setOfficialMatches] = useState<OfficialSummary[]>([]);
  const [sourceRevision, setSourceRevision] = useState("");
  const [sourceKind, setSourceKind] = useState("manufacturer_https");
  const [stageId, setStageId] = useState("");
  const [officialValidated, setOfficialValidated] = useState(false);
  const [diff, setDiff] = useState<DiffEntry[]>([]);
  const [message, setMessage] = useState("");
  const [collision, setCollision] = useState<CatalogIdentityCollisionError | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = useCallback(async () => {
    const result = await api<{ local: LocalEntry[]; history: History; evidence: Evidence[] }>();
    setLocal(result.local); setHistory(result.history); setEvidence(result.evidence);
  }, []);
  useEffect(() => {
    void api<{ local: LocalEntry[]; history: History; evidence: Evidence[] }>()
      .then(result => { setLocal(result.local); setHistory(result.history); setEvidence(result.evidence); })
      .catch(error => setMessage(String(error)));
  }, []);
  async function run(task: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await task(); }
    catch (error) {
      if (error instanceof CatalogIdentityCollisionError) {
        setCollision(error);
        setOfficialValidated(false);
        setStageId("");
      }
      setMessage(error instanceof Error ? error.message : String(error));
    }
    finally { setBusy(false); }
  }
  const setRecord = (key: keyof LocalEntry["record"], value: string) => { setPreview([]); setForm(current => ({ ...current, record: { ...current.record, [key]: value } })); };
  const setProfile = (key: string, value: unknown) => { setPreview([]); setForm(current => ({ ...current, profile: { ...current.profile, [key]: value } })); };
  const selectedBatch = batch.length ? batch : [form];
  async function loadOfficial(vendor: string, icpn: string) {
    setOfficial(await api<OfficialEntry>("official", undefined, `?vendor=${encodeURIComponent(vendor)}&icpn=${encodeURIComponent(icpn)}`));
    setOfficialVendor(vendor); setOfficialICPN(icpn); setOfficialValidated(false); setStageId("");
  }
  async function importFile(file: File) {
    const content = await file.text();
    const parsed = file.name.toLowerCase().endsWith(".csv") ? parseCsv(content) : JSON.parse(content);
    const entries = Array.isArray(parsed) ? parsed : parsed.local ?? parsed.official;
    if (!Array.isArray(entries)) throw new Error("JSON import must contain a local array");
    if (entries.length && entries.every(entry => entry && typeof entry === "object" && "qualification" in entry)) {
      setOfficialBatch(entries); setBatch([]); setPreview([]); setOfficialValidated(false); setStageId("");
      setMessage(`${entries.length} official candidates loaded. Review before staging.`);
      return;
    }
    setOfficialBatch([]);
    setBatch(entries); setPreview([]); setMessage(`${entries.length} rows loaded. Validate before saving.`);
  }
  function download(format: "json" | "csv", records: LocalEntry[] = local) {
    const payload = format === "json" ? JSON.stringify({ local: records }, null, 2) : [
      "vendor,identifier,family,package,flash_size,profile_id,provider_id,operations",
      ...records.map(item => [item.record.vendor, item.record.identifier, item.record.family, item.record.package, item.record.flash_size, String(item.profile.profile_id ?? ""), String(item.profile.provider_id ?? ""), Array.isArray(item.profile.operations) ? item.profile.operations.join("|") : ""].map(value => `"${value.replaceAll('"', '""')}"`).join(",")),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([payload], { type: format === "json" ? "application/json" : "text/csv" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `plasma-local-catalog.${format}`; anchor.click();
    URL.revokeObjectURL(url);
  }
  return <main className="icManagement">
    <ThemeSwitch />
    <header><div><p>ICPN CATALOG · CONTROL STATION</p><h1>IC Management</h1><span>Official revisions and Controller-local records are stored separately.</span></div><Link href="/devices">Open IC Selector →</Link></header>
    {collision && <section role="alert" aria-label="Catalog identity conflict" className="managementCollision">
      <h2>Official Catalog update blocked: {collision.total} customer part number conflict(s)</h2>
      <p>Official and LOCAL records have the same manufacturer and exact ICPN. Your local IC and custom Profile are unchanged. No Official revision was activated.</p>
      <p><strong>Resolve manually:</strong> Export your Local Catalog JSON as a backup. Open each local record, use "Copy as new" to save a customer-specific identifier, verify the copied Profile, and only then explicitly delete the old local entry. Retry Official validation after every conflict has been resolved. Nothing is automatically renamed, deleted, or promoted.</p>
      <div className="managementActions">
        <button type="button" disabled={busy} onClick={() => void run(async () => {
          const latest = await api<{ local: LocalEntry[] }>();
          setLocal(latest.local);
          download("json", latest.local);
          setMessage("Downloaded current Local Catalog JSON backup. Keep it safe before changing customer part numbers.");
        })}>Export Local Catalog JSON</button>
        <button type="button" onClick={() => setCollision(null)}>Dismiss conflict notice</button>
      </div>
      <div className="managementCollisionList">
        {collision.conflicts.map(item => <div key={`${item.manufacturer}:${item.exact_icpn}`}>
          <strong>{item.manufacturer} · {item.exact_icpn}</strong>
          <span>LOCAL r{item.local_revision ?? "?"} · Profile {item.local_profile_id ?? "—"}</span>
          <button type="button" onClick={() => {
            const match = local.find(entry => entry.record.vendor.toLowerCase() === item.manufacturer.toLowerCase() && entry.record.identifier.toLowerCase() === item.exact_icpn.toLowerCase());
            if (!match) { setMessage("Local record not loaded. Reload IC Management before resolving."); return; }
            setForm(match); setBatch([]); setPreview([]); setSearch(match.record.identifier);
            document.getElementById("local-ic-editor")?.scrollIntoView({ behavior: "smooth" });
          }}>View customer IC</button>
        </div>)}
      </div>
      {collision.truncated && <p>Only the first {collision.conflicts.length} conflicts are shown. Resolve these and revalidate to identify remaining conflicts.</p>}
    </section>}
    {message && <p role="status" className="managementMessage">{message}</p>}
    <section><h2>Controller-local ICs <small>LOCAL / UNVERIFIED</small></h2>
      <input aria-label="Search local ICs" placeholder="Search vendor or ICPN" value={search} onChange={event => setSearch(event.target.value)} />
      <div className="managementList">{local.filter(item => `${item.record.vendor} ${item.record.identifier}`.toLowerCase().includes(search.toLowerCase())).map(item =>
        <button type="button" key={`${item.record.vendor}:${item.record.identifier}`} onClick={() => { setForm(item); setBatch([]); setPreview([]); }}>
          <b>{item.record.identifier}</b><span>{item.record.vendor} · {item.record.family}</span><em>LOCAL / UNVERIFIED · r{item.revision}</em>
        </button>)}</div>
      <button type="button" onClick={() => { setForm(empty); setBatch([]); }}>New IC</button>
      <button type="button" onClick={() => { setForm({ ...form, record: { ...form.record, identifier: "" } }); setBatch([]); }}>Copy as new</button>
      {form.revision && <button disabled={busy} type="button" onClick={() => void run(async () => { await api("delete-local", { vendor: form.record.vendor, icpn: form.record.identifier }); setForm(empty); setPreview([]); await reload(); setMessage("Local IC deleted."); })}>Delete selected local IC</button>}
    </section>
    <section id="local-ic-editor"><h2>Record &amp; Custom Programming Profile</h2>
      <div className="managementGrid">{(["vendor", "identifier", "family", "package", "flash_size"] as const).map(key => <label key={key}>{key.replace("_", " ")}<input value={form.record[key]} onChange={event => setRecord(key, event.target.value)} /></label>)}
        <label>Profile ID<input value={String(form.profile.profile_id ?? "")} onChange={event => setProfile("profile_id", event.target.value)} /></label>
        <label>Provider ID<input value={String(form.profile.provider_id ?? "")} onChange={event => setProfile("provider_id", event.target.value)} /></label>
        <label>Operations (display only)<input value={Array.isArray(form.profile.operations) ? form.profile.operations.join(", ") : ""} onChange={event => setProfile("operations", event.target.value.split(",").map(value => value.trim()).filter(Boolean))} /></label>
        <label>Source Evidence references<input value={Array.isArray(form.profile.source_evidence) ? form.profile.source_evidence.join(", ") : ""} onChange={event => setProfile("source_evidence", event.target.value.split(",").map(value => value.trim()).filter(Boolean))} /></label>
      </div>
      <details><summary>Advanced profile fields and Source Evidence</summary><textarea aria-label="Advanced profile JSON" value={JSON.stringify(form.profile, null, 2)} onChange={event => { try { const profile = JSON.parse(event.target.value); setPreview([]); setForm(current => ({ ...current, profile })); } catch { /* Keep the last valid object. */ } }} /></details>
      <div className="managementActions"><button disabled={busy} onClick={() => void run(async () => { const result = await api<{ changes: LocalEntry[] }>("validate", { entries: selectedBatch }); setPreview(result.changes); setMessage("Validation passed. Review the changes below."); })}>Validate</button>
      <button disabled={busy || !preview.length} onClick={() => void run(async () => { await api("local", { entries: selectedBatch }); setBatch([]); setPreview([]); await reload(); setMessage("Local records saved atomically."); })}>Save local changes</button></div>
    </section>
    <section><h2>Import / Export</h2><label>CSV or JSON batch<input type="file" accept=".csv,.json" onChange={event => { const file = event.target.files?.[0]; if (file) void run(() => importFile(file)); }} /></label>
      <div className="managementActions"><button onClick={() => download("csv")}>Export CSV</button><button onClick={() => download("json")}>Export JSON</button>
        <button onClick={() => void run(async () => {
          const result = await api<{ official: unknown[] }>("export");
          const url = URL.createObjectURL(new Blob([JSON.stringify(result.official, null, 2)], { type: "application/json" }));
          const anchor = document.createElement("a"); anchor.href = url; anchor.download = "plasma-official-catalog.json"; anchor.click(); URL.revokeObjectURL(url);
        })}>Export official JSON</button></div>
      {preview.length > 0 && <div className="managementList" aria-label="Changes preview">{preview.map((item, index) => <p key={index}>{item.change} · {item.record.vendor} {item.record.identifier} · r{item.revision}</p>)}</div>}
      {officialBatch.length > 0 && <div className="managementList" aria-label="Official changes preview">{officialBatch.map((item, index) => <p key={index}>OFFICIAL CANDIDATE · {String(item.record.vendor)} {String(item.record.identifier)}</p>)}
        <button disabled={busy} onClick={() => void run(async () => { await api("validate-official", { changes: officialBatch }); setCollision(null); setOfficialValidated(true); setMessage("Official batch validated. Review the candidates before staging."); })}>Validate official batch</button>
        <button disabled={busy || !officialValidated} onClick={() => void run(async () => { const result = await api<{ stage_id: string }>("stage", { changes: officialBatch }); setStageId(result.stage_id); setMessage("Official batch staged atomically."); })}>Stage official batch</button>
        <button disabled={busy || !stageId} onClick={() => void run(async () => { const result = await api<{ revision: string }>("publish", { stage_id: stageId }); setStageId(""); setOfficialBatch([]); await reload(); setMessage(`Published ${result.revision}`); })}>Publish official batch</button></div>}
    </section>
    <section><h2>Official Catalog · Validate / Stage / Publish</h2><p>Official Exact ICPN qualification remains governed by source evidence and the existing Publisher. Local profiles never grant Job admission.</p>
      <div className="managementActions"><input aria-label="Search official ICs" placeholder="Vendor, family or exact ICPN" value={officialSearch} onChange={event => setOfficialSearch(event.target.value)} />
        <button disabled={busy || officialSearch.trim().length < 2} onClick={() => void run(async () => { const result = await api<{ official: OfficialSummary[]; total_count: number }>("search", undefined, `?q=${encodeURIComponent(officialSearch)}`); setOfficialMatches(result.official); setMessage(`${result.total_count} official matches`); })}>Search official</button></div>
      <div className="managementList">{officialMatches.map(item => <button key={`${item.vendor}:${item.identifier}`} onClick={() => void run(() => loadOfficial(item.vendor, item.identifier))}>
        <b>{item.identifier}</b><span>{item.vendor} · {item.family} · L{item.level}</span><em>OFFICIAL · {item.source} · {history?.active_revision?.slice(0, 12)}</em>
      </button>)}</div>
      <div className="managementGrid"><label>Manufacturer<input value={officialVendor} onChange={event => setOfficialVendor(event.target.value)} /></label><label>Exact ICPN<input value={officialICPN} onChange={event => setOfficialICPN(event.target.value)} /></label></div>
      <button disabled={busy} onClick={() => void run(() => loadOfficial(officialVendor, officialICPN))}>Load official record</button>
      {official && <><p>Editing candidate from revision <code>{official.revision.slice(0, 12)}</code>. Published snapshot stays immutable.</p>
        <button type="button" onClick={() => { setForm({ record: { vendor: String(official.record.vendor ?? ""), identifier: "", family: String(official.record.family ?? ""), package: String(official.record.package ?? ""), flash_size: String(official.record.flash_size ?? "") }, profile: { profile_id: "", provider_id: "", operations: [] } }); setBatch([]); setPreview([]); setMessage("Official identity copied into a new LOCAL / UNVERIFIED draft. Enter a new exact ICPN."); }}>Copy official as new local IC</button>
        <div className="managementGrid"><label>Source revision<input value={sourceRevision} onChange={event => setSourceRevision(event.target.value)} /></label>
          <label>Evidence kind<select value={sourceKind} onChange={event => setSourceKind(event.target.value)}><option value="manufacturer_https">Manufacturer HTTPS</option><option value="locked_production_identity">Locked production identity</option></select></label></div>
        <button disabled={busy || !sourceRevision} onClick={() => void run(async () => { const result = await api<{ evidence_id: string }>("evidence", { record: official.record, kind: sourceKind, source_revision: sourceRevision }); await reload(); setMessage(`Evidence ${result.evidence_id} acquired or reused from local store.`); })}>Acquire / reuse Source Evidence</button>
        <div className="managementGrid">{(["family", "package", "flash_size", "source_reference"] as const).map(key => <label key={key}>{key.replace("_", " ")}<input value={String(official.record[key] ?? "")} onChange={event => { setStageId(""); setOfficialValidated(false); setOfficial({ ...official, record: { ...official.record, [key]: event.target.value } }); }} /></label>)}</div>
        <details><summary>Advanced official fields and Evidence</summary><textarea aria-label="Official candidate JSON" defaultValue={JSON.stringify({ record: official.record, qualification: official.qualification }, null, 2)} onBlur={event => { try { const value = JSON.parse(event.target.value); setStageId(""); setOfficialValidated(false); setOfficial({ ...official, record: value.record, qualification: value.qualification }); } catch { setMessage("Invalid candidate JSON"); } }} /></details>
        <div className="managementActions"><button disabled={busy} onClick={() => void run(async () => { await api("validate-official", { changes: [{ record: official.record, qualification: official.qualification }] }); setCollision(null); setOfficialValidated(true); setMessage("Official candidate validated."); })}>Validate</button>
          <button disabled={busy || !officialValidated} onClick={() => void run(async () => { const result = await api<{ stage_id: string }>("stage", { changes: [{ record: official.record, qualification: official.qualification }] }); setStageId(result.stage_id); setMessage("Official candidate staged."); })}>Stage</button>
          <button disabled={busy || !stageId} onClick={() => void run(async () => { const result = await api<{ revision: string }>("publish", { stage_id: stageId }); setStageId(""); await reload(); setMessage(`Published ${result.revision}. IC Selector reads the active revision immediately.`); })}>Publish</button></div></>}
    </section>
    <section><h2>Source Evidence</h2><div className="managementList">{evidence.map(item => <p key={item.evidence_id}><code>{item.evidence_id.slice(0, 16)}</code> · {item.authority} · {item.source_revision}<br />{item.reference}</p>)}</div></section>
    <section><h2>Revision History / Diff / Audit</h2><p>Active revision <code>{history?.active_revision ?? "—"}</code></p>
      <div className="managementList">{history?.revisions.map(item => <div key={item.revision}><code>{item.revision.slice(0, 16)}</code> · {item.count} ICs
        <button disabled={busy || item.revision === history.active_revision} onClick={() => void run(async () => { const result = await api<{ changes: typeof diff }>("diff", undefined, `?revision=${item.revision}`); setDiff(result.changes); })}>Diff</button>
        <button disabled={busy || item.revision === history.active_revision} onClick={() => void run(async () => { await api("rollback", { revision: item.revision }); await reload(); setMessage(`Rolled back to ${item.revision}`); })}>Rollback</button></div>)}</div>
      {diff.map((item, index) => <details key={index}><summary>{item.status} · {item.vendor} {item.identifier}</summary>
        <p>Record: {item.before?.record?.family ? String(item.before.record.family) : "—"} → {item.after?.record?.family ? String(item.after.record.family) : "—"}</p>
        <p>Qualification: {String(item.before?.qualification?.catalog_level ?? "—")} → {String(item.after?.qualification?.catalog_level ?? "—")}</p>
        <pre>{JSON.stringify({ before: item.before, after: item.after }, null, 2)}</pre>
      </details>)}
      <details><summary>Audit ({history?.audit.length ?? 0})</summary>{history?.audit.map((item, index) => <p key={index}>{item.created_at} · {item.action} · {item.actor} · {item.detail}</p>)}</details>
    </section>
  </main>;
}

export default function ICManagementPage() {
  const { hydrated } = useWorkspaceSession();
  if (!hydrated) return <main className="icManagement" aria-busy="true">Resolving Control Station routing…</main>;
  return <ManagementContent />;
}
