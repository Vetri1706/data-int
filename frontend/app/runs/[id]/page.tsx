"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { runs, collections, datasets, toEntityRecord, type WorkflowRun, type RunEvent, type DatasetRecord, type Dataset } from "@/lib/api";
import { DataTable } from "@/components/dataset/DataTable";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import type { EntityRecord } from "@/lib/types";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [versions, setVersions] = useState<Dataset[]>([]);
  const [review, setReview] = useState<EntityRecord[]>([]);
  const [selected, setSelected] = useState<EntityRecord | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const retryWithLocalModel = async () => {
    if (!run) return;
    setRetrying(true);
    try {
      const collection = await collections.get(run.collection_id);
      router.push(`/collections/new?${new URLSearchParams({ prompt: collection.prompt, local: "1", domains: (collection.data_contract.source_policy?.domain_filters ?? []).join(", ") })}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Cannot load the original requirement"); }
    finally { setRetrying(false); }
  };
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [r, h, ds] = await Promise.all([runs.get(id), runs.history(id), datasets.list()]);
        if (!active) return;
        setRun(r); setEvents(h.data); setVersions(ds.data.filter(d => d.run_id === id));
        setReview(h.review_candidates.map((raw, i) => toEntityRecord({ id: `review-${i}`, canonical_name: String(raw.canonical_name), status: "needs_review", confidence_score: null, primary_attributes: raw } as DatasetRecord)));
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Run unavailable"); }
    };
    void load();
    const timer = setInterval(load, 2000);
    return () => { active = false; clearInterval(timer); };
  }, [id]);
  return <main className="space-y-5">
    <h1 className="text-2xl font-semibold">Execution history</h1>
    {error && <p role="alert">{error}</p>}
    {run && <p>{run.status} · {run.records_verified} accepted records · Run {id}</p>}
    {run?.error_message && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{run.error_message}</p>}
    {run?.status === "failed" && <div className="space-y-2">
      <button className="rounded border px-4 py-2 disabled:opacity-50" disabled={retrying} onClick={retryWithLocalModel}>{retrying ? "Opening setup…" : "Retry with configured local model"}</button>
      <p className="text-sm text-[var(--muted)]">Opens a new collection with the original requirement. Review the model and sources before running.</p>
    </div>}
    {run && !["completed", "partial", "exhausted", "failed", "cancelled"].includes(run.status) && <button className="rounded border px-4 py-2" onClick={async () => { try { const result = await runs.cancel(id); setRun({ ...run, status: result.status }); } catch (e) { setError(e instanceof Error ? e.message : "Cancellation failed"); } }}>Cancel run</button>}
    {versions.map(ds => <Link key={ds.id} href={`/datasets/${ds.id}`} className="block text-blue-700">Inspect saved dataset: {ds.name}</Link>)}
    <ol className="space-y-3">{events.map(event => <li key={event.id} className="rounded border p-3 text-sm">
      <p className="font-semibold">{event.type} · {new Date(event.created_at).toLocaleString()}</p>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(Object.fromEntries(Object.entries(event.payload).filter(([k]) => !["records", "review_candidates"].includes(k))), null, 2)}</pre>
    </li>)}</ol>
    {review.length > 0 && <section><h2 className="font-semibold">Review candidates — excluded from accepted datasets</h2><DataTable data={review} onSelectEntity={setSelected} /></section>}
    <EvidenceDrawer entity={selected} onClose={() => setSelected(null)} />
  </main>;
}
