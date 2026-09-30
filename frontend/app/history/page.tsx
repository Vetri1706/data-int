"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { collections, runs } from "@/lib/api";
import { TaskSummary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function HistoryPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = "History — Datavault";
    let mounted = true;
    collections.list().then(async cols => (await Promise.all(cols.data.map(async col => {
      const list = await runs.list(col.id);
      return list.data.map(run => ({ id: run.id, collection_id: col.id, timestamp: run.started_at, prompt: col.title,
        category: col.data_contract?.entity_type ?? "entity", records_count: run.records_verified,
        sources_count: 0, total_latency_ms: run.completed_at ? Date.parse(run.completed_at) - Date.parse(run.started_at) : 0,
        triggered_grounding: true, workflow_summary: run.current_stage,
        status: ({ completed: "Completed", partial: "Partial", exhausted: "Exhausted", failed: "Failed", cancelled: "Cancelled" } as Record<string, TaskSummary["status"]>)[run.status] ?? "Running" }));
    }))).flat().sort((a,b) => b.timestamp.localeCompare(a.timestamp))).then((data) => {
      if (mounted) setTasks(data);
    }).catch((cause: unknown) => {
      if (mounted) setError(cause instanceof Error ? cause.message : "Could not load history.");
    }).finally(() => {
      if (mounted) setLoading(false);
    });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="mx-auto w-full max-w-[1400px] 2xl:max-w-[1680px]">
      <header className="mb-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Audit trail</div>
        <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">History</h1>
        <p className="mt-1 text-[12px] text-[#66758a]">Past requirements and their extraction outcomes.</p>
      </header>

      {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
      <section className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white" aria-labelledby="history-list-heading">
        <h2 id="history-list-heading" className="sr-only">Collection execution history</h2>
        {loading && <p role="status" className="p-5 text-sm text-[#66758a]">Loading history…</p>}
        {!loading && !error && tasks.length === 0 && <p className="p-5 text-sm text-[#66758a]">No collection history yet.</p>}
        <ol className="divide-y divide-[#e8edf3]">
          {tasks.map((task) => {
            const statusTone =
              task.status === "Completed"
                ? "bg-[#2aa36b]"
                : task.status === "Running"
                ? "bg-[#2d78e8]"
                : task.status === "Failed"
                ? "bg-[#c64b57]"
                : "bg-[#8290a3]";
            return (
              <li key={task.id} className="grid gap-3 px-4 py-4 hover:bg-[#f8fafc] sm:grid-cols-[12px_1fr_auto] sm:items-start sm:px-5">
                <span className={`mt-1.5 h-2 w-2 rounded-full ${statusTone}`} aria-hidden="true" />
                <div className="min-w-0">
                  <Link href={`/runs/${task.id}`} className="block truncate text-[12px] font-semibold text-[#172a44] hover:text-[#246bde]">{task.prompt}</Link>
                  <p className="mt-1 text-[10px] text-[#66758a]">{task.records_count} records · {task.status}</p>
                  <p className="mt-1.5 truncate font-mono text-[9px] text-[#8794a7]">{task.id.slice(0, 12)} · {task.workflow_summary}</p>
                </div>
                <div className="flex items-center gap-3 sm:justify-end">
                  <span className="text-[10px] text-[#7c899c]">{formatDate(task.timestamp)}</span>
                  <Link href={`/runs/${task.id}`} aria-label={`Inspect ${task.prompt}`} className="flex h-7 w-7 items-center justify-center rounded-[6px] border border-[#d6dfe9] bg-white text-[#53647c] hover:bg-[#f3f6f9] hover:text-[#17345f]">
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
