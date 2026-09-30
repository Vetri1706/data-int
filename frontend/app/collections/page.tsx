"use client";

import React, { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  CheckSquare,
  Edit2,
  Loader2,
  Play,
  Plus,
  RotateCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { collections, fetchTasks } from "@/lib/api";
import { TaskSummary } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { DeleteCollectionDialog } from "@/components/collection/DeleteCollectionDialog";
import { RenameCollectionDialog } from "@/components/collection/RenameCollectionDialog";

type StatusTab = "all" | "completed" | "running" | "needs_review" | "failed" | "partial" | "exhausted" | "cancelled";

function CollectionsContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("query")?.trim() ?? "";

  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(initialQuery);
  const [statusTab, setStatusTab] = useState<StatusTab>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Modal states
  const [deleteTarget, setDeleteTarget] = useState<{ id?: string; title: string; count?: number; isBulk?: boolean } | null>(null);
  const [renameTarget, setRenameTarget] = useState<{ id: string; title: string } | null>(null);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  const loadData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    try {
      setError(null);
      const data = await fetchTasks();
      setTasks(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load collections.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    document.title = "Collections — Datavault";
    const timer = setTimeout(() => { void loadData(); }, 0);
    return () => clearTimeout(timer);
  }, []);

  // Compute status counts
  const counts = useMemo(() => {
    const c = { all: tasks.length, completed: 0, running: 0, needs_review: 0, failed: 0, partial: 0, exhausted: 0, cancelled: 0 };
    for (const t of tasks) {
      const s = t.status.toLowerCase();
      if (s === "completed") c.completed++;
      else if (s === "running") c.running++;
      else if (s === "failed") c.failed++;
      else if (s === "partial") c.partial++;
      else if (s === "exhausted") c.exhausted++;
      else if (s === "cancelled") c.cancelled++;
      else c.needs_review++;
    }
    return c;
  }, [tasks]);

  // Filter tasks based on search & active status tab
  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const s = task.status.toLowerCase();
      const matchesTab = statusTab === "all" || (statusTab === "needs_review"
        ? ["draft", "needsreview", "needs_review"].includes(s) : s === statusTab);

      if (!matchesTab) return false;

      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        task.prompt.toLowerCase().includes(q) ||
        task.category.toLowerCase().includes(q) ||
        task.status.toLowerCase().includes(q)
      );
    });
  }, [tasks, statusTab, search]);

  // Bulk selection helpers
  const allFilteredSelected =
    filteredTasks.length > 0 && filteredTasks.every((t) => selectedIds.has(t.id));

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set());
    } else {
      const next = new Set(selectedIds);
      for (const t of filteredTasks) next.add(t.id);
      setSelectedIds(next);
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  // Actions
  const handleRerun = async (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    e?.preventDefault();
    try {
      setRunningIds((prev) => new Set(prev).add(id));
      await collections.triggerRun(id);
      setNotice({ type: "success", message: "Collection run started. Background workers are extracting evidence." });
      await loadData();
    } catch (err: unknown) {
      setNotice({ type: "error", message: err instanceof Error ? err.message : "Failed to start collection run." });
    } finally {
      setRunningIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    if (deleteTarget.isBulk) {
      const ids = Array.from(selectedIds);
      await collections.bulkDelete(ids);
      setSelectedIds(new Set());
      setNotice({ type: "success", message: `Deleted ${ids.length} collections and their datasets.` });
    } else if (deleteTarget.id) {
      await collections.delete(deleteTarget.id);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(deleteTarget.id!);
        return next;
      });
      setNotice({ type: "success", message: `Collection “${deleteTarget.title}” deleted successfully.` });
    }
    await loadData();
  };

  const handleSaveRename = async (newTitle: string) => {
    if (!renameTarget) return;
    await collections.update(renameTarget.id, { title: newTitle });
    setNotice({ type: "success", message: `Collection renamed to “${newTitle}”.` });
    await loadData();
  };

  return (
    <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none">
      {/* Page Header */}
      <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">
            Library & Management
          </div>
          <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">
            Collections
          </h1>
          <p className="mt-1 text-[12px] text-[#66758a]">
            Organize, monitor, execute, and manage business data requirements.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => loadData(true)}
            disabled={refreshing}
            aria-label="Refresh collection list"
            className="flex h-9 items-center gap-1.5 rounded-[7px] border border-[#d6dfe9] bg-white px-3 text-[11px] font-semibold text-[#53647c] transition-colors hover:bg-[#f6f8fb] hover:text-[#10213a] disabled:opacity-50"
          >
            <RotateCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-[#246bde]" : ""}`} />
            <span>Refresh</span>
          </button>
          <Link
            href="/collections/new"
            className="flex h-9 items-center gap-1.5 rounded-[7px] bg-[#246bde] px-4 text-[11px] font-semibold text-white transition-colors hover:bg-[#1959c2] active:bg-[#154ca5]"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New collection</span>
          </Link>
        </div>
      </header>

      {/* Global Alerts / Notices */}
      {notice && (
        <div
          role="status"
          className={`mb-4 flex items-center justify-between rounded-[8px] border p-3 text-[12px] font-medium shadow-sm transition-all ${
            notice.type === "success"
              ? "border-[#bfe5d0] bg-[#eefaf3] text-[#1a7042]"
              : "border-[#f4c8ce] bg-[#fff5f6] text-[#b43242]"
          }`}
        >
          <span>{notice.message}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="rounded p-1 hover:bg-black/5"
            aria-label="Dismiss alert"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-[8px] border border-[#f4c8ce] bg-[#fff5f6] p-3.5 text-[12px] text-[#b43242]"
        >
          Could not load collections: {error}
        </div>
      )}

      {/* Control Bar: Status Tabs & Search Input */}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        {/* Status Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1 rounded-[8px] border border-[#dce4ed] bg-[#f8fafc] p-1 text-[11px] font-medium text-[#53647c]">
          {[
            { id: "all", label: "All", count: counts.all },
            { id: "completed", label: "Completed", count: counts.completed },
            { id: "running", label: "Running", count: counts.running },
            { id: "needs_review", label: "Draft / Review", count: counts.needs_review },
            { id: "partial", label: "Partial", count: counts.partial },
            { id: "exhausted", label: "Exhausted", count: counts.exhausted },
            { id: "cancelled", label: "Cancelled", count: counts.cancelled },
            { id: "failed", label: "Failed", count: counts.failed },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setStatusTab(tab.id as StatusTab)}
              className={`flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 transition-all ${
                statusTab === tab.id
                  ? "bg-white font-semibold text-[#17345f] shadow-[0_1px_3px_rgba(20,40,70,0.08)]"
                  : "hover:text-[#17345f]"
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                  statusTab === tab.id
                    ? "bg-[#eef3f9] text-[#17345f]"
                    : "bg-[#e8edf4] text-[#6b7b92]"
                }`}
              >
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        {/* Search Filter */}
        <div className="relative w-full max-w-[340px]">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#7c899c]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search requirement, category, title…"
            className="h-9 w-full rounded-[7px] border border-[#d6dfe9] bg-white pl-9 pr-9 text-[11px] text-[#172a44] outline-none placeholder:text-[#8b98aa] focus:border-[#6d9ee8] focus:ring-3 focus:ring-[#246bde]/10"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#7c899c] hover:text-[#10213a]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Bulk Management Action Bar */}
      {selectedIds.size > 0 && (
        <div className="mb-3 flex items-center justify-between rounded-[8px] border border-[#fed7dc] bg-[#fff5f6] px-4 py-2.5 shadow-sm">
          <div className="flex items-center gap-2 text-[12px] font-semibold text-[#9b2c39]">
            <CheckSquare className="h-4 w-4" />
            <span>
              {selectedIds.size} collection{selectedIds.size > 1 ? "s" : ""} selected
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="rounded-[6px] border border-[#e4a8b0] bg-white px-2.5 py-1 text-[11px] font-medium text-[#7a202c] hover:bg-[#fff9fa]"
            >
              Deselect all
            </button>
            <button
              type="button"
              onClick={() =>
                setDeleteTarget({
                  title: `${selectedIds.size} collections`,
                  count: selectedIds.size,
                  isBulk: true,
                })
              }
              className="flex items-center gap-1.5 rounded-[6px] bg-[#c64b57] px-3 py-1 text-[11px] font-semibold text-white shadow-sm hover:bg-[#b03d48]"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>Delete selected</span>
            </button>
          </div>
        </div>
      )}

      {/* Main Table */}
      <section
        aria-labelledby="collection-list-heading"
        className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white shadow-sm"
      >
        <h2 id="collection-list-heading" className="sr-only">
          Collection list
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-[11px]">
            <caption className="sr-only">
              Collections with status, category, record count, and management actions.
            </caption>
            <thead className="border-b border-[#dce4ed] bg-[#f6f8fb] text-[#617189]">
              <tr>
                <th scope="col" className="w-10 px-3 py-2.5 text-center">
                  <input
                    type="checkbox"
                    aria-label="Select all visible collections"
                    checked={allFilteredSelected}
                    onChange={toggleSelectAll}
                    className="h-3.5 w-3.5 rounded border-[#aebbc9] text-[#246bde] focus:ring-[#246bde]"
                  />
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Requirement / Title
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Status
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Category
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Records
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Updated
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e8edf3]">
              {filteredTasks.map((task) => {
                const isSelected = selectedIds.has(task.id);
                const isRunning = runningIds.has(task.id) || task.status.toLowerCase() === "running";
                const isCompleted = task.status.toLowerCase() === "completed";
                const isFailed = task.status.toLowerCase() === "failed";

                const statusTone = isCompleted
                  ? "bg-[#2aa36b]"
                  : isRunning
                  ? "bg-[#2d78e8]"
                  : isFailed
                  ? "bg-[#c64b57]"
                  : "bg-[#8290a3]";

                return (
                  <tr
                    key={task.id}
                    className={`transition-colors hover:bg-[#f8fafc] ${
                      isSelected ? "bg-[#f4f8fe]" : ""
                    }`}
                  >
                    {/* Row Select Checkbox */}
                    <td className="px-3 py-3 text-center">
                      <input
                        type="checkbox"
                        aria-label={`Select collection ${task.prompt}`}
                        checked={isSelected}
                        onChange={() => toggleSelect(task.id)}
                        className="h-3.5 w-3.5 rounded border-[#aebbc9] text-[#246bde] focus:ring-[#246bde]"
                      />
                    </td>

                    {/* Requirement Prompt & Title */}
                    <td className="max-w-[420px] px-3 py-3 font-semibold text-[#172a44]">
                      <Link
                        href={`/collections/${task.id}`}
                        className="block truncate hover:text-[#246bde] hover:underline"
                        title={task.prompt}
                      >
                        {task.prompt}
                      </Link>
                    </td>

                    {/* Status Badge */}
                    <td className="px-3 py-3 text-[#53647c]">
                      <span className="inline-flex items-center gap-2">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${statusTone} ${
                            isRunning ? "animate-pulse" : ""
                          }`}
                          aria-hidden="true"
                        />
                        <span className="capitalize">{task.status}</span>
                      </span>
                    </td>

                    {/* Category */}
                    <td className="px-3 py-3 text-[#53647c]">
                      <span className="rounded bg-[#edf2f7] px-2 py-0.5 text-[10px] font-medium text-[#485970]">
                        {task.category}
                      </span>
                    </td>

                    {/* Record count */}
                    <td className="px-3 py-3 font-mono font-medium text-[#23354f]">
                      {task.records_count ? (
                        <span className="font-semibold text-[#197248]">
                          {task.records_count} records
                        </span>
                      ) : (
                        <span className="text-[#8c9ba5]">—</span>
                      )}
                    </td>

                    {/* Updated date */}
                    <td className="px-3 py-3 text-[#607089]">
                      {formatDate(task.timestamp)}
                    </td>

                    {/* Quick Row Management Actions */}
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Rerun Button */}
                        <button
                          type="button"
                          onClick={(e) => handleRerun(task.id, e)}
                          disabled={isRunning}
                          title="Rerun collection extraction"
                          aria-label={`Rerun collection ${task.prompt}`}
                          className="flex h-7 w-7 items-center justify-center rounded-[5px] border border-[#d6dfe9] text-[#53647c] transition-colors hover:border-[#b4c7dc] hover:bg-[#f2f7fc] hover:text-[#246bde] disabled:opacity-40"
                        >
                          {isRunning ? (
                            <Loader2 className="h-3 w-3 animate-spin text-[#246bde]" />
                          ) : (
                            <Play className="h-3 w-3 fill-current" />
                          )}
                        </button>

                        {/* Rename / Edit Title Button */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenameTarget({ id: task.id, title: task.prompt });
                          }}
                          title="Rename collection"
                          aria-label={`Rename collection ${task.prompt}`}
                          className="flex h-7 w-7 items-center justify-center rounded-[5px] border border-[#d6dfe9] text-[#53647c] transition-colors hover:border-[#b4c7dc] hover:bg-[#f2f7fc] hover:text-[#246bde]"
                        >
                          <Edit2 className="h-3 w-3" />
                        </button>

                        {/* Delete Button */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget({
                              id: task.id,
                              title: task.prompt,
                              count: task.records_count,
                            });
                          }}
                          title="Delete collection"
                          aria-label={`Delete collection ${task.prompt}`}
                          className="flex h-7 w-7 items-center justify-center rounded-[5px] border border-[#ebd0d4] text-[#b83848] transition-colors hover:border-[#df9ba4] hover:bg-[#fff0f2] hover:text-[#94202e]"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!loading && filteredTasks.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center">
                    <p className="font-semibold text-[#23354f]">No collections match your criteria.</p>
                    <div className="mt-2 flex items-center justify-center gap-3">
                      {(search || statusTab !== "all") && (
                        <button
                          type="button"
                          onClick={() => {
                            setSearch("");
                            setStatusTab("all");
                          }}
                          className="text-[11px] font-semibold text-[#246bde] hover:underline"
                        >
                          Clear filters
                        </button>
                      )}
                      <Link
                        href="/collections/new"
                        className="text-[11px] font-semibold text-[#246bde] hover:underline"
                      >
                        Create new collection
                      </Link>
                    </div>
                  </td>
                </tr>
              )}

              {loading && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-[#718096]" aria-live="polite">
                    <div className="flex items-center justify-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-[#246bde]" />
                      <span>Loading collections…</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <DeleteCollectionDialog
          isOpen={true}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleConfirmDelete}
          title={deleteTarget.title}
          count={deleteTarget.count}
          isBulk={deleteTarget.isBulk}
        />
      )}

      {/* Rename Modal */}
      {renameTarget && (
        <RenameCollectionDialog
          isOpen={true}
          onClose={() => setRenameTarget(null)}
          onSave={handleSaveRename}
          initialTitle={renameTarget.title}
        />
      )}
    </div>
  );
}

export default function CollectionsPage() {
  return (
    <Suspense
      fallback={
        <div className="py-12 text-center text-[12px] text-[#718096]">
          Loading collections…
        </div>
      }
    >
      <CollectionsContent />
    </Suspense>
  );
}
