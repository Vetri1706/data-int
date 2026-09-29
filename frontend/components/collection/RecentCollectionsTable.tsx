"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Trash2 } from "lucide-react";
import { collections, fetchTasks } from "@/lib/api";
import type { TaskSummary } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { DeleteCollectionDialog } from "@/components/collection/DeleteCollectionDialog";

export function RecentCollectionsTable() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string; count?: number } | null>(null);

  const loadTasks = async () => {
    try {
      const data = await fetchTasks();
      setTasks(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load collections.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const rows = tasks.slice(0, 5).map((task) => ({
    id: task.id,
    title: task.prompt,
    records: task.records_count,
    status: task.status.toLowerCase(),
    updated_at: task.timestamp,
  }));

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await collections.delete(deleteTarget.id);
    await loadTasks();
  };

  return (
    <section className="min-w-0" aria-labelledby="recent-collections-heading">
      <div className="overflow-hidden rounded-[10px] border border-[#e0e7ef] bg-white">
        <div className="flex items-center justify-between border-b border-[#edf1f5] px-5 py-4 2xl:px-6 2xl:py-5">
          <h2 id="recent-collections-heading" className="text-[13px] font-semibold text-[#10213a] 2xl:text-[15px]">
            Recent collections
          </h2>
          <Link
            href="/collections"
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold text-[#53647c] transition-colors hover:bg-[#f3f6f9] hover:text-[#246bde] 2xl:text-[12px]"
          >
            View all
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm 2xl:min-w-[820px]">
            <caption className="sr-only">Recently created data collections</caption>
            <thead>
              <tr className="border-b border-[#edf1f5] bg-[#fafbfd] text-[10px] font-semibold text-[#738198] 2xl:text-[11px]">
                <th scope="col" className="px-5 py-3 font-semibold 2xl:px-6 2xl:py-3.5">Name</th>
                <th scope="col" className="px-4 py-3 font-semibold 2xl:py-3.5">Status</th>
                <th scope="col" className="px-4 py-3 font-semibold 2xl:py-3.5">Records</th>
                <th scope="col" className="px-4 py-3 font-semibold 2xl:py-3.5">Updated</th>
                <th scope="col" className="w-20 px-4 py-3 text-right"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#edf1f5]">
              {(error || loading || !rows.length) && (
                <tr>
                  <td colSpan={5} className="p-5 text-xs text-[#607089]" role={error ? "alert" : undefined}>
                    {error ? `Could not load collections: ${error}` : loading ? "Loading collections…" : "No collections yet."}
                  </td>
                </tr>
              )}
              {rows.map((collection) => {
                const isCompleted = collection.status === "completed";
                const isRunning = collection.status === "running";

                return (
                  <tr key={collection.id} className="group transition-colors hover:bg-[#f8fafc]">
                    <td className="px-5 py-3.5 2xl:px-6 2xl:py-4.5">
                      <Link
                        href={`/collections/${collection.id}`}
                        className="font-medium text-[#20324c] hover:text-[#246bde] hover:underline 2xl:text-[14px]"
                      >
                        {collection.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3.5 2xl:py-4.5">
                      <div className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#52627a] 2xl:text-[12px]">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            isCompleted
                              ? "bg-[#2aa66a]"
                              : isRunning
                              ? "bg-[#246bde]"
                              : "bg-[#93a1b4]"
                          }`}
                        />
                        <span className="capitalize">{collection.status.replace("_", " ")}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-[11px] font-medium text-[#42536b] 2xl:py-4.5 2xl:text-[12px]">
                      {collection.records || "—"}
                    </td>
                    <td className="px-4 py-3.5 text-[11px] text-[#6a788c] 2xl:py-4.5 2xl:text-[12px]">
                      {formatDate(collection.updated_at)}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() =>
                            setDeleteTarget({
                              id: collection.id,
                              title: collection.title,
                              count: collection.records,
                            })
                          }
                          title="Delete collection"
                          aria-label={`Delete ${collection.title}`}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#9ca7b6] hover:bg-[#fff0f2] hover:text-[#c64b57]"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        <Link
                          href={`/collections/${collection.id}`}
                          aria-label={`Open ${collection.title}`}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#8a97a9] hover:bg-[#edf2f7] hover:text-[#246bde]"
                        >
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <DeleteCollectionDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title={deleteTarget?.title ?? ""}
        count={deleteTarget?.count}
      />
    </section>
  );
}
