"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronDown,
  Download,
  Edit2,
  ExternalLink,
  Loader2,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import {
  collections,
  fetchTaskById,
  getExportCsvUrl,
  getExportJsonUrl,
} from "@/lib/api";
import { EntityRecord, GroundingResponse } from "@/lib/types";
import { DataTable } from "@/components/dataset/DataTable";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import { DeleteCollectionDialog } from "@/components/collection/DeleteCollectionDialog";
import { RenameCollectionDialog } from "@/components/collection/RenameCollectionDialog";
import SmoothTab from "@/components/kokonutui/smooth-tab";

type TabId = "results" | "briefing" | "contract" | "sources" | "activity";

const TABS: { id: TabId; label: string }[] = [
  { id: "results", label: "Results" },
  { id: "briefing", label: "Briefing" },
  { id: "contract", label: "Data contract" },
  { id: "sources", label: "Sources" },
  { id: "activity", label: "Activity" },
];

export default function CollectionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [collection, setCollection] = useState<GroundingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("results");
  const [selectedEntity, setSelectedEntity] = useState<EntityRecord | null>(null);

  // Management modal states
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [banner, setBanner] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadDetails = async () => {
    try {
      const response = await fetchTaskById(id);
      setCollection(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load collection.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetails();
  }, [id]);

  const records = collection?.records ?? [];
  const title = collection?.title ?? "Collection";

  useEffect(() => {
    document.title = `${title} — Datavault`;
  }, [title]);

  const handleRerun = async () => {
    try {
      setIsRerunning(true);
      await collections.triggerRun(id);
      setBanner({
        type: "success",
        text: "Collection execution started. Background reasoning layer is active.",
      });
      await loadDetails();
    } catch (err: unknown) {
      setBanner({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to trigger run.",
      });
    } finally {
      setIsRerunning(false);
    }
  };

  const handleRename = async (newTitle: string) => {
    await collections.update(id, { title: newTitle });
    setBanner({ type: "success", text: `Renamed to “${newTitle}”.` });
    await loadDetails();
  };

  const handleDelete = async () => {
    await collections.delete(id);
    router.push("/collections");
  };

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none" aria-live="polite">
        <div className="h-3 w-56 rounded bg-[#e5eaf0]" />
        <div className="mt-4 h-7 w-[min(520px,80%)] rounded bg-[#dfe6ee]" />
        <div className="mt-8 h-10 rounded-[7px] border border-[#e0e6ed] bg-white" />
        <div className="mt-4 h-80 rounded-[9px] border border-[#e0e6ed] bg-white" />
        <span className="sr-only">Loading collection results</span>
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-[#e2c3c8] bg-white p-6 text-sm text-[#9b3543]">
        Could not load collection: {error}
      </div>
    );
  }

  const isCompleted = collection?.status?.toLowerCase() === "completed";
  const isRunning = isRerunning || collection?.status?.toLowerCase() === "running";

  return (
    <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none">
      {/* Header with Navigation and Management Actions */}
      <header className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[10px] text-[#7c899c]">
            <Link href="/collections" className="font-medium hover:text-[#246bde]">
              Collections
            </Link>
            <span aria-hidden="true">›</span>
            <span aria-current="page" className="max-w-[360px] truncate text-[#52627a]">
              {title}
            </span>
          </nav>

          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <h1 className="text-[23px] font-bold tracking-[-0.035em] text-[#10213a] 2xl:text-[30px]">
              {title}
            </h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#e9f6ef] px-2 py-1 text-[10px] font-semibold text-[#197248]">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isCompleted ? "bg-[#2aa36b]" : isRunning ? "bg-[#2d78e8] animate-pulse" : "bg-[#8290a3]"
                }`}
                aria-hidden="true"
              />
              <span className="capitalize">{collection?.status ?? "Unknown"}</span>
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[#607089]">
            {collection?.total_records ?? 0} records <span aria-hidden="true">·</span>{" "}
            {collection?.updated_at
              ? `Updated ${new Date(collection.updated_at).toLocaleString()}`
              : "No recorded update"}
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
          {/* Rerun Button */}
          <button
            type="button"
            onClick={handleRerun}
            disabled={isRunning}
            className="flex h-9 items-center gap-1.5 rounded-[7px] border border-[#d6dfe9] bg-white px-3.5 text-[11px] font-semibold text-[#53647c] transition-colors hover:bg-[#f6f8fb] hover:text-[#246bde] disabled:opacity-50"
            title="Rerun this collection pipeline"
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-[#246bde]" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
            <span>{isRunning ? "Running…" : "Rerun"}</span>
          </button>

          {/* Rename Button */}
          <button
            type="button"
            onClick={() => setIsRenameOpen(true)}
            className="flex h-9 items-center gap-1.5 rounded-[7px] border border-[#d6dfe9] bg-white px-3 text-[11px] font-semibold text-[#53647c] transition-colors hover:bg-[#f6f8fb] hover:text-[#10213a]"
            title="Rename collection"
          >
            <Edit2 className="h-3.5 w-3.5" />
            <span>Rename</span>
          </button>

          {/* Export Dropdown */}
          {collection?.dataset_id && (
            <details className="group relative">
              <summary className="flex h-9 list-none items-center gap-2 rounded-[7px] bg-[#17345f] px-4 text-[11px] font-semibold text-white hover:bg-[#102b50] [&::-webkit-details-marker]:hidden">
                <Download className="h-3.5 w-3.5" />
                Export
                <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
              </summary>
              <div className="absolute right-0 z-30 mt-1.5 w-56 rounded-[8px] border border-[#d8e1eb] bg-white p-1.5 shadow-[0_12px_28px_rgba(32,49,71,0.14)]">
                <a
                  href={getExportCsvUrl(collection.dataset_id)}
                  download
                  className="flex items-center gap-2 rounded-[6px] px-3 py-2 text-[11px] font-medium text-[#41526a] hover:bg-[#f3f6f9] hover:text-[#17345f]"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download CSV
                </a>
                <a
                  href={getExportJsonUrl(collection.dataset_id)}
                  download
                  className="flex items-center gap-2 rounded-[6px] px-3 py-2 text-[11px] font-medium text-[#41526a] hover:bg-[#f3f6f9] hover:text-[#17345f]"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download JSON with evidence
                </a>
              </div>
            </details>
          )}

          {/* Delete Button */}
          <button
            type="button"
            onClick={() => setIsDeleteOpen(true)}
            className="flex h-9 items-center gap-1.5 rounded-[7px] border border-[#ebd0d4] bg-white px-3 text-[11px] font-semibold text-[#b83848] transition-colors hover:border-[#df9ba4] hover:bg-[#fff0f2] hover:text-[#94202e]"
            title="Delete this collection"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>Delete</span>
          </button>
        </div>
      </header>

      {/* Action Feedback Banner */}
      {banner && (
        <div
          role="status"
          className={`mb-4 flex items-center justify-between rounded-[8px] border p-3 text-[12px] font-medium shadow-sm transition-all ${
            banner.type === "success"
              ? "border-[#bfe5d0] bg-[#eefaf3] text-[#1a7042]"
              : "border-[#f4c8ce] bg-[#fff5f6] text-[#b43242]"
          }`}
        >
          <span>{banner.text}</span>
          <button
            type="button"
            onClick={() => setBanner(null)}
            className="rounded p-1 hover:bg-black/5"
            aria-label="Dismiss banner"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="mb-4 overflow-x-auto">
        <SmoothTab
          ariaLabel="Collection detail views"
          items={TABS.map((tab) => ({
            id: tab.id,
            title: tab.label,
            count: tab.id === "sources" ? collection?.sources?.length ?? 0 : undefined,
          }))}
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as TabId)}
        />
      </div>

      {/* Tab Panels */}
      <div id={`panel-${activeTab}`} role="tabpanel" aria-labelledby={`tab-${activeTab}`} tabIndex={0}>
        {activeTab === "results" && <DataTable data={records} onSelectEntity={setSelectedEntity} />}

        {activeTab === "briefing" && (
          <section className="rounded-[9px] border border-[#dce4ed] bg-white p-5 sm:p-6" aria-labelledby="briefing-heading">
            <h2 id="briefing-heading" className="text-[15px] font-bold text-[#10213a]">Executive briefing</h2>
            <p className="mt-3 max-w-[860px] whitespace-pre-wrap text-[12px] leading-6 text-[#4e6078]">
              {collection?.summary_briefing || "No briefing is available for this collection."}
            </p>
          </section>
        )}

        {activeTab === "contract" && (
          <section className="rounded-[9px] border border-[#dce4ed] bg-white p-5 sm:p-6" aria-labelledby="contract-heading">
            <h2 id="contract-heading" className="text-[15px] font-bold text-[#10213a]">Data requirement contract</h2>
            <p className="mt-1 text-[11px] text-[#66758a]">Machine-readable fields and constraints used for extraction and verification.</p>
            <pre className="mt-4 overflow-x-auto rounded-[7px] border border-[#dce4ed] bg-[#f6f8fb] p-4 font-mono text-[11px] leading-5 text-[#334760]">
              {JSON.stringify(collection?.contract || {}, null, 2)}
            </pre>
          </section>
        )}

        {activeTab === "sources" && (
          <section className="rounded-[9px] border border-[#dce4ed] bg-white p-5 sm:p-6" aria-labelledby="sources-panel-heading">
            <h2 id="sources-panel-heading" className="text-[15px] font-bold text-[#10213a]">Permitted sources</h2>
            {collection?.sources?.length ? (
              <ul className="mt-3 divide-y divide-[#e8edf3] border-y border-[#e8edf3]">
                {collection.sources.map((source) => (
                  <li key={source.url} className="flex flex-col gap-2 py-3 text-[11px] sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="font-semibold text-[#23354f]">{source.title}</div>
                      <a href={source.url} target="_blank" rel="noopener noreferrer" className="mt-0.5 flex items-center gap-1 text-[#246bde] hover:underline">
                        <span className="truncate">{source.url}</span>
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    </div>
                    <div className="flex shrink-0 gap-4 text-[#66758a]">
                      <span>Authority {typeof source.authority_score === "number" ? `${Math.round(source.authority_score * 100)}%` : "Not measured"}</span>
                      <span className="font-mono font-semibold text-[#197248]">{source.live_status_code ? `HTTP ${source.live_status_code}` : "Not checked"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-5 text-[12px] text-[#66758a]">No source records were returned for this collection.</p>
            )}
          </section>
        )}

        {activeTab === "activity" && (
          <section className="rounded-[9px] border border-[#dce4ed] bg-white p-5 sm:p-6" aria-labelledby="activity-heading">
            <h2 id="activity-heading" className="text-[15px] font-bold text-[#10213a]">Workflow activity</h2>
            <p className="mt-1 text-[11px] text-[#66758a]">Execution history for the collection pipeline.</p>
            {collection?.workflow?.stages?.length ? (
              <ol className="mt-4 divide-y divide-[#e8edf3] border-y border-[#e8edf3]">
                {collection.workflow.stages.map((stage) => (
                  <li key={stage.stage_id} className="flex items-start justify-between gap-4 py-3 text-[11px]">
                    <div className="flex min-w-0 gap-3">
                      <span className="font-mono font-semibold text-[#246bde]">{String(stage.stage_id).padStart(2, "0")}</span>
                      <div>
                        <div className="font-semibold text-[#23354f]">{stage.stage_name}</div>
                        <p className="mt-0.5 leading-4 text-[#66758a]">{stage.details}</p>
                      </div>
                    </div>
                    <span className="shrink-0 font-mono text-[#7c899c]">{stage.duration_ms} ms</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-5 text-[12px] text-[#66758a]">No execution events were recorded.</p>
            )}
          </section>
        )}
      </div>

      <EvidenceDrawer entity={selectedEntity} onClose={() => setSelectedEntity(null)} />

      {/* Delete Confirmation Modal */}
      <DeleteCollectionDialog
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        onConfirm={handleDelete}
        title={title}
        count={collection?.total_records}
      />

      {/* Rename Modal */}
      <RenameCollectionDialog
        isOpen={isRenameOpen}
        onClose={() => setIsRenameOpen(false)}
        onSave={handleRename}
        initialTitle={title}
      />
    </div>
  );
}
