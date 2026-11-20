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
type LinkedProfileEntry = LocalEntry & {
  origin: "CUSTOMER";
  ic_origin: "OFFICIAL" | "CUSTOMER";
  profile_origin: "CUSTOMER";
  link_status: "ACTIVE" | "PENDING_OFFICIAL";
  verification: "UNVERIFIED";
};
type History = { active_revision: string | null; revisions: Array<{ revision: string; count: number }>; audit: Array<{ action: string; actor: string; revision: string; detail: string; created_at: string }> };
type OfficialEntry = { record: Record<string, unknown>; qualification: Record<string, unknown>; revision: string };
type Evidence = { evidence_id: string; authority: string; reference: string; source_revision: string; acquired_at: string };
type DiffEntry = { vendor: string; identifier: string; status: string; before?: { record: Record<string, unknown>; qualification: Record<string, unknown> }; after?: { record: Record<string, unknown>; qualification: Record<string, unknown> } };
type OfficialSummary = { vendor: string; identifier: string; family: string; source: string; level: number };
const base = "/api/manager/catalog/management";
const empty: LocalEntry = { record: { vendor: "", identifier: "", family: "", package: "", flash_size: "" }, profile: { profile_id: "", provider_id: "", operations: [] } };

async function api<T>(action = "", body?: object, query = ""): Promise<T> {
  const response = await fetch(`${base}${action ? `/${action}` : ""}${query}`, {
    method: body ? "POST" : "GET", cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const result = await response.json() as T & { error?: { message?: string } };
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
  const [linkedProfiles, setLinkedProfiles] = useState<LinkedProfileEntry[]>([]);
  const [sameIcConfirmed, setSameIcConfirmed] = useState(false);
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
  const [busy, setBusy] = useState(false);
  const reload = useCallback(async () => {
    const result = await api<{ local: LocalEntry[]; linked_profiles?: LinkedProfileEntry[]; history: History; evidence: Evidence[] }>();
    setLocal(result.local); setLinkedProfiles(result.linked_profiles ?? []); setHistory(result.history); setEvidence(result.evidence);
  }, []);
  useEffect(() => {
    void api<{ local: LocalEntry[]; linked_profiles?: LinkedProfileEntry[]; history: History; evidence: Evidence[] }>()
      .then(result => { setLocal(result.local); setLinkedProfiles(result.linked_profiles ?? []); setHistory(result.history); setEvidence(result.evidence); })
      .catch(error => setMessage(String(error)));
  }, []);
  async function run(task: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await task(); }
    catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
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
    <header><div><p>ICPN CATALOG · CONTROL STATION</p><h1>IC Management</h1><span>Official revisions and Controller-local records are stored separately. The same Manufacturer and Exact ICPN may exist in both, with independent Profiles and qualification.</span></div><Link href="/devices">Open IC Selector →</Link></header>
    {message && <p role="status" className="managementMessage">{message}</p>}
    <section><h2>Controller-local ICs <small>LOCAL / UNVERIFIED</small></h2>
      <input aria-label="Search local ICs" placeholder="Search vendor or ICPN" value={search} onChange={event => setSearch(event.target.value)} />
      <div className="managementList">{local.filter(item => `${item.record.vendor} ${item.record.identifier}`.toLowerCase().includes(search.toLowerCase())).map(item =>
        <button type="button" key={`${item.record.vendor}:${item.record.identifier}`} onClick={() => { setForm(item); setBatch([]); setPreview([]); setSameIcConfirmed(false); }}>
          <b>{item.record.identifier}</b><span>{item.record.vendor} · {item.record.family}</span><em>CUSTOMER IC / UNVERIFIED · r{item.revision}</em>
        </button>)}</div>
      <button type="button" onClick={() => { setForm(empty); setBatch([]); }}>New IC</button>
      <button type="button" onClick={() => { setForm({ ...form, record: { ...form.record, identifier: "" } }); setBatch([]); }}>Copy as new</button>
      {form.revision && <button disabled={busy} type="button" onClick={() => void run(async () => { await api("delete-local", { vendor: form.record.vendor, icpn: form.record.identifier }); setForm(empty); setPreview([]); await reload(); setMessage("Local IC deleted."); })}>Delete selected local IC</button>}
    </section>
    <section><h2>Official IC with Customer Profile <small>OFFICIAL IC · CUSTOMER PROFILE</small></h2>
      <p>IC identity and Qualification belong to the Official Catalog. Linked customer Profiles remain CUSTOMER / UNVERIFIED, not Job authorization.</p>
      <div className="managementList" role="list" aria-label="Customer Profiles linked to Official ICs">{linkedProfiles.map(item => <p role="listitem" key={`${item.record.vendor}:${item.record.identifier}`}>
        <b>{item.record.identifier}</b> · {item.record.vendor} · <strong>{item.link_status === "ACTIVE" ? "OFFICIAL IC" : "CUSTOMER IC · OFFICIAL PENDING"}</strong> · CUSTOMER PROFILE <code>{String(item.profile.profile_id ?? "—")}</code> · r{item.revision} · UNVERIFIED
      </p>)}</div>
    </section>
    <section id="local-ic-editor"><h2>Record &amp; Custom Programming Profile</h2>
      <div className="managementGrid">{(["vendor", "identifier", "family", "package", "flash_size"] as const).map(key => <label key={key}>{key.replace("_", " ")}<input value={form.record[key]} onChange={event => setRecord(key, event.target.value)} /></label>)}
        <label>Profile ID<input value={String(form.profile.profile_id ?? "")} onChange={event => setProfile("profile_id", event.target.value)} /></label>
        <label>Provider ID<input value={String(form.profile.provider_id ?? "")} onChange={event => setProfile("provider_id", event.target.value)} /></label>
        <label>Operations (display only)<input value={Array.isArray(form.profile.operations) ? form.profile.operations.join(", ") : ""} onChange={event => setProfile("operations", event.target.value.split(",").map(value => value.trim()).filter(Boolean))} /></label>
        <label>Source Evidence references<input value={Array.isArray(form.profile.source_evidence) ? form.profile.source_evidence.join(", ") : ""} onChange={event => setProfile("source_evidence", event.target.value.split(",").map(value => value.trim()).filter(Boolean))} /></label>
      </div>
      <details><summary>Advanced profile fields and Source Evidence</summary><textarea aria-label="Advanced profile JSON" value={JSON.stringify(form.profile, null, 2)} onChange={event => { try { const profile = JSON.parse(event.target.value); setPreview([]); setForm(current => ({ ...current, profile })); } catch { /* Keep the last valid object. */ } }} /></details>
      {form.revision && <div className="managementLinkReview">
        <p><strong>Link to Official IC:</strong> only for the same physical chip and exact Manufacturer/ICPN already published in the Official Catalog. Customer Profile never becomes Official Qualification.</p>
        <label><input type="checkbox" checked={sameIcConfirmed} onChange={event => setSameIcConfirmed(event.target.checked)} />I verified that this CUSTOMER IC and the published OFFICIAL IC are the same physical device.</label>
        <button type="button" disabled={busy || !sameIcConfirmed} onClick={() => void run(async () => {
          const result = await api<{ link: { profile_id: string } }>("link-local-official", {
            vendor: form.record.vendor, icpn: form.record.identifier,
            expected_local_revision: form.revision, confirmed_same_ic: true,
          });
          setForm(empty); setSameIcConfirmed(false); setPreview([]); setBatch([]);
          await reload(); setMessage(`Linked OFFICIAL IC to CUSTOMER Profile ${result.link.profile_id}. No programming qualification changed.`);
        })}>Link to Official IC (preserve Customer Profile)</button>
      </div>}
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
        <button disabled={busy} onClick={() => void run(async () => { await api("validate-official", { changes: officialBatch }); setOfficialValidated(true); setMessage("Official batch validated. Review the candidates before staging."); })}>Validate official batch</button>
        <button disabled={busy || !officialValidated} onClick={() => void run(async () => { const result = await api<{ stage_id: string }>("stage", { changes: officialBatch }); setStageId(result.stage_id); setMessage("Official batch staged atomically."); })}>Stage official batch</button>
        <button disabled={busy || !stageId} onClick={() => void run(async () => { const result = await api<{ revision: string }>("publish", { stage_id: stageId }); setStageId(""); setOfficialBatch([]); await reload(); setMessage(`Published ${result.revision}`); })}>Publish official batch</button></div>}
    </section>
    <section><h2>Official Catalog · Validate / Stage / Publish</h2><p>Official Exact ICPN qualification remains governed by source evidence and the existing Publisher. Local profiles never grant Job admission.</p>
      <div className="managementActions"><input aria-label="Search official ICs" placeholder="Vendor, family or exact ICPN" value={officialSearch} onChange={event => setOfficialSearch(event.target.value)} />
        <button disabled={busy || officialSearch.trim().length < 2} onClick={() => void run(async () => { const result = await api<{ official: OfficialSummary[]; total_count: number }>("search", undefined, `?q=${encodeURIComponent(officialSearch)}`); setOfficialMatches(result.official); setMessage(`${result.total_count} official matches`); })}>Search official</button></div>
      <div className="managementList">{officialMatches.map(item => <button key={`${item.vendor}:${item.identifier}`} onClick={() => void run(() => loadOfficial(item.vendor, item.identifier))}>
        <b>{item.identifier}</b><span>{item.vendor} · {item.family} · L{item.level}</span><em>OFFICIAL IC{linkedProfiles.some(link => link.link_status === "ACTIVE" && link.record.vendor.toLowerCase() === item.vendor.toLowerCase() && link.record.identifier.toLowerCase() === item.identifier.toLowerCase()) ? " · CUSTOMER PROFILE" : ""} · {item.source} · {history?.active_revision?.slice(0, 12)}</em>
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
        <div className="managementActions"><button disabled={busy} onClick={() => void run(async () => { await api("validate-official", { changes: [{ record: official.record, qualification: official.qualification }] }); setOfficialValidated(true); setMessage("Official candidate validated."); })}>Validate</button>
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
