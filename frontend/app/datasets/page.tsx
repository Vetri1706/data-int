"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Download, ExternalLink } from "lucide-react";
import { datasets as datasetApi, type Dataset, getExportCsvUrl, getExportJsonUrl } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    document.title = "Datasets — Datavault";
    let active = true;
    datasetApi.list().then(({ data }) => { if (active) setDatasets(data); })
      .catch((error: Error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, []);



  return (
    <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none">
      <header className="mb-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Structured output</div>
        <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">Datasets</h1>
        <p className="mt-1 text-[12px] text-[#66758a]">Verified records ready for inspection or export.</p>
      </header>

      {error && <p role="alert" className="mb-4 text-sm text-[#9b3543]">Could not load datasets: {error}</p>}
      <section aria-labelledby="datasets-heading" className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white">
        <h2 id="datasets-heading" className="sr-only">Available datasets</h2>
        <ul className="divide-y divide-[#e8edf3]">
          {datasets.map((dataset) => (
            <li key={dataset.id} className="flex flex-col gap-4 px-4 py-4 hover:bg-[#f8fafc] sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="min-w-0">
                <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-[#6d7e94]">Dataset {dataset.id.slice(0, 8)}</div>
                <Link href={`/datasets/${dataset.id}`} className="mt-1.5 block truncate text-[13px] font-semibold text-[#172a44] hover:text-[#246bde]">{dataset.name}</Link>
                <p className="mt-1 text-[11px] text-[#66758a]">{dataset.record_count} records <span aria-hidden="true">·</span> {formatDate(dataset.created_at)}</p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Link href={`/datasets/${dataset.id}`} className="flex h-8 items-center gap-1.5 rounded-[6px] border border-[#d6dfe9] bg-white px-3 text-[10px] font-semibold text-[#53647c] hover:bg-[#f3f6f9] hover:text-[#17345f]">
                  Inspect <ExternalLink className="h-3 w-3" />
                </Link>
                <a href={getExportCsvUrl(dataset.id)} download className="flex h-8 items-center gap-1.5 rounded-[6px] border border-[#d6dfe9] bg-white px-3 text-[10px] font-semibold text-[#53647c] hover:bg-[#f3f6f9] hover:text-[#17345f]">
                  <Download className="h-3 w-3" /> CSV
                </a>
                <a href={getExportJsonUrl(dataset.id)} download className="flex h-8 items-center gap-1.5 rounded-[6px] border border-[#d6dfe9] bg-white px-3 text-[10px] font-semibold text-[#53647c] hover:bg-[#f3f6f9] hover:text-[#17345f]">
                  <Download className="h-3 w-3" /> JSON
                </a>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
