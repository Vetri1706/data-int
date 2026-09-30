"use client";

import React, { useEffect, useState } from "react";
import { FileText, Database, CheckCircle2, AlertTriangle } from "lucide-react";
import { collections, datasets, runs, type DatasetRecord } from "@/lib/api";
import { NumberTicker } from "@/components/ui/number-ticker";

export function MetricCards() {
  const [summary, setSummary] = useState<{collections: number; reviewCount: number; records: DatasetRecord[]} | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([collections.list(), datasets.list()]).then(async ([cols, list]) => {
      const latest = [...new Map([...list.data].reverse().map((ds) => [ds.collection_id, ds])).values()];
      const responses = await Promise.all(latest.map((ds) => datasets.records(ds.id)));
      const reviews = await Promise.all(cols.data.map(async col => {
        const list = await runs.list(col.id);
        return list.data[0] ? (await runs.history(list.data[0].id)).review_candidates.length : 0;
      }));
      if (active) setSummary({ collections: cols.data.length, reviewCount: reviews.reduce((a,b) => a+b,0), records: responses.flatMap((r) => r.data) });
    }).catch((error: Error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, []);
  const records = summary?.records ?? [];
  const coverages = records.map(r => (r.primary_attributes.verification as {field_coverage?: number} | undefined)?.field_coverage).filter((v): v is number => typeof v === "number");
  const averageCoverage = coverages.length ? Math.round(coverages.reduce((a,b) => a+b,0) / coverages.length * 100) : null;

  const METRICS = [
    {
      id: "collections",
      label: "Collections",
      value: summary?.collections ?? null,
      suffix: "",
      icon: FileText,
      tone: "text-[#557196] bg-[#edf3fa]",
    },
    {
      id: "records",
      label: "Records loaded",
      value: summary ? records.length : null,
      suffix: "",
      icon: Database,
      tone: "text-[#246bde] bg-[#edf3ff]",
    },
    {
      id: "accuracy",
      label: "Supported field coverage",
      value: averageCoverage,
      suffix: "%",
      icon: CheckCircle2,
      tone: "text-[#238a59] bg-[#edf8f2]",
    },
    {
      id: "review",
      label: "Need review",
      value: summary?.reviewCount ?? null,
      suffix: "",
      icon: AlertTriangle,
      tone: "text-[#b97908] bg-[#fff7e8]",
    },
  ];

  return (
    <section className="min-w-0" aria-labelledby="workspace-snapshot-heading">
      <div className="mb-3 flex items-center justify-between">
        <h2 id="workspace-snapshot-heading" className="text-[13px] font-semibold text-[#10213a] 2xl:text-[15px]">
          Workspace snapshot
        </h2>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[#8794a7]">Current view</span>
      </div>
      {error && <p role="alert" className="mb-3 text-xs text-[#9b3543]">Metrics unavailable: {error}</p>}
      <div className="grid grid-cols-2 gap-3">
      {METRICS.map((metric) => {
        const Icon = metric.icon;
        return (
          <div
            key={metric.id}
            className="min-h-[126px] rounded-[10px] border border-[#e0e7ef] bg-white p-4 2xl:min-h-[154px] 2xl:p-5"
          >
            <div className="flex items-start justify-between">
              <div
                className="font-mono text-[24px] font-semibold tracking-[-0.04em] text-[#10213a] 2xl:text-[30px]"
                aria-label={`${metric.value ?? "Not available"}${metric.value === null ? "" : metric.suffix} ${metric.label}`}
              >
                {metric.value === null ? <span>—</span> : <NumberTicker value={metric.value} aria-hidden="true" className="text-[#10213a]" />}
                <span aria-hidden="true">{metric.value === null ? "" : metric.suffix}</span>
              </div>
              <div className={`flex h-8 w-8 items-center justify-center rounded-[7px] 2xl:h-9 2xl:w-9 ${metric.tone}`}>
                <Icon className="h-4 w-4 stroke-[1.8] 2xl:h-[18px] 2xl:w-[18px]" />
              </div>
            </div>
            <div className="mt-4 text-[11px] font-medium text-[#5e6f86] 2xl:mt-5 2xl:text-[13px]">{metric.label}</div>
          </div>
        );
      })}
      </div>
    </section>
  );
}
