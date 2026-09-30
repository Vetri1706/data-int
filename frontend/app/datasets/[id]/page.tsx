"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { datasets, toEntityRecord, getExportCsvUrl, getExportJsonUrl, type Dataset } from "@/lib/api";
import { DataTable } from "@/components/dataset/DataTable";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import type { EntityRecord } from "@/lib/types";

export default function DatasetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [records, setRecords] = useState<EntityRecord[]>([]);
  const [selected, setSelected] = useState<EntityRecord | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([datasets.get(id), datasets.records(id)]).then(([ds, rows]) => {
      if (active) { setDataset(ds); setRecords(rows.data.map(toEntityRecord)); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [id]);
  if (error) return <p role="alert">{error}</p>;
  if (!dataset) return <p role="status">Loading dataset version…</p>;
  return <main className="space-y-5">
    <Link href={`/collections/${dataset.collection_id}`} className="text-blue-700">Collection</Link>
    <h1 className="text-2xl font-semibold">{dataset.name}</h1>
    <p className="text-sm">Saved {new Date(dataset.created_at).toLocaleString()} · Version {dataset.id}</p>
    {dataset.schema?.verification_method !== "typed-claims-v1" && <p className="rounded border border-amber-300 p-3 text-sm">Legacy dataset: these records have not passed the typed claim verifier.</p>}
    <div className="flex gap-4 text-sm"><a href={getExportCsvUrl(id)}>Export this version as CSV</a><a href={getExportJsonUrl(id)}>Export this version as JSON</a>{dataset.run_id && <Link href={`/runs/${dataset.run_id}`}>Inspect this run</Link>}</div>
    <DataTable data={records} onSelectEntity={setSelected} />
    <EvidenceDrawer entity={selected} onClose={() => setSelected(null)} />
  </main>;
}
