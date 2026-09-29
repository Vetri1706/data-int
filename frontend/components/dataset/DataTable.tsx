"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  ColumnDef,
  RowSelectionState,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, Columns3, Filter, Search, X } from "lucide-react";
import { EntityRecord } from "@/lib/types";

interface DataTableProps {
  data: EntityRecord[];
  onSelectEntity: (entity: EntityRecord) => void;
}

type StatusFilter = "all" | "verified" | "needs_review";

const SYSTEM_KEYS = new Set([
  "canonical_name",
  "name",
  "confidence_breakdown",
  "confidence_score",
  "chunk_id",
  "evidence_excerpt",
  "extraction_confidence",
  "source_url",
  "status",
  "id",
  "created_at",
  "updated_at",
  "reachability",
]);

function formatAttributeHeader(key: string): string {
  return key
    .replace(/[_\s]+/g, " ")
    .trim()
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function DataTable({ data, onSelectEntity }: DataTableProps) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});

  const filteredData = useMemo(
    () =>
      statusFilter === "all"
        ? data
        : data.filter((record) => record.status === statusFilter),
    [data, statusFilter]
  );

  // Dynamically compute the top 2-3 most frequent business attribute keys across records
  const dynamicAttributeKeys = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const record of data) {
      if (!record.primary_attributes) continue;
      for (const [key, val] of Object.entries(record.primary_attributes)) {
        if (SYSTEM_KEYS.has(key)) continue;
        if (val !== null && val !== undefined && val !== "") {
          counts[key] = (counts[key] || 0) + 1;
        }
      }
    }
    const sorted = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    if (sorted.length === 0) {
      return ["industry", "location"];
    }
    return sorted.slice(0, 3);
  }, [data]);

  const columns = useMemo<ColumnDef<EntityRecord>[]>(() => {
    const cols: ColumnDef<EntityRecord>[] = [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            aria-label="Select all records on this page"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            className="h-3.5 w-3.5 rounded border-[#aebbc9] text-[#246bde] focus:ring-[#246bde]"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            aria-label={`Select ${row.original.canonical_name}`}
            checked={row.getIsSelected()}
            disabled={!row.getCanSelect()}
            onChange={row.getToggleSelectedHandler()}
            className="h-3.5 w-3.5 rounded border-[#aebbc9] text-[#246bde] focus:ring-[#246bde]"
          />
        ),
        size: 38,
      },
      {
        accessorKey: "canonical_name",
        header: "Entity / Name",
        cell: ({ row }) => (
          <button
            type="button"
            onClick={() => onSelectEntity(row.original)}
            className="text-left font-semibold text-[#172a44] hover:text-[#246bde]"
          >
            {row.original.canonical_name}
          </button>
        ),
      },
    ];

    // Dynamic schema business attributes
    for (const attrKey of dynamicAttributeKeys) {
      cols.push({
        id: attrKey,
        header: formatAttributeHeader(attrKey),
        cell: ({ row }) => {
          const val = row.original.primary_attributes?.[attrKey];
          return (
            <span className="text-[#56677f]" title={val ? String(val) : undefined}>
              {val || "—"}
            </span>
          );
        },
      });
    }

    // Corroborating evidence
    cols.push({
      id: "evidence",
      header: "Evidence",
      cell: ({ row }) => {
        const count = row.original.provenance?.source_urls?.length || 0;
        return (
          <button
            type="button"
            onClick={() => onSelectEntity(row.original)}
            className="font-medium text-[#53647c] underline-offset-4 hover:text-[#246bde] hover:underline"
            aria-label={`View ${count} evidence sources for ${row.original.canonical_name}`}
          >
            {count} {count === 1 ? "source" : "sources"}
          </button>
        );
      },
    });

    // Confidence metric
    cols.push({
      accessorKey: "confidence_score",
      header: "Confidence",
      cell: ({ row }) => {
        const score = row.original.confidence_score;
        const pct = typeof score === "number" ? Math.round(score * 100) : null;
        return (
          <div className="flex items-center gap-2 font-medium text-[#53647c]">
            <div className="h-1.5 w-12 overflow-hidden rounded-full bg-[#e3e8ee]">
              <div
                className={`h-full rounded-full ${
                  pct !== null && pct >= 70
                    ? "bg-[#2aa36b]"
                    : pct !== null && pct >= 40
                    ? "bg-[#246bde]"
                    : "bg-[#e1a514]"
                }`}
                style={{ width: `${pct ?? 0}%` }}
              />
            </div>
            <span className="text-[10px] tabular-nums">{pct !== null ? `${pct}%` : "—"}</span>
          </div>
        );
      },
    });

    // Verification status
    cols.push({
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const isVerified = row.original.status === "verified";
        return (
          <div className="flex items-center gap-2 font-medium text-[#53647c]">
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                isVerified ? "bg-[#2aa36b]" : "bg-[#e1a514]"
              }`}
            />
            <span>
              {isVerified
                ? "Verified"
                : row.original.status === "draft"
                ? "Draft"
                : row.original.status === "running"
                ? "Running"
                : "Needs review"}
            </span>
          </div>
        );
      },
    });

    return cols;
  }, [dynamicAttributeKeys, onSelectEntity]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { globalFilter, rowSelection, columnVisibility },
    onRowSelectionChange: setRowSelection,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 8 } },
  });

  useEffect(() => {
    table.setPageIndex(0);
  }, [globalFilter, statusFilter, table]);

  const cycleStatusFilter = () => {
    setStatusFilter((current) =>
      current === "all" ? "verified" : current === "verified" ? "needs_review" : "all"
    );
  };

  const keyColumnsOnly = dynamicAttributeKeys.some((k) => columnVisibility[k] === false);
  const toggleColumns = () => {
    setColumnVisibility((current) => {
      const updated = { ...current };
      for (const attr of dynamicAttributeKeys.slice(1)) {
        updated[attr] = keyColumnsOnly;
      }
      return updated;
    });
  };

  const filteredCount = table.getFilteredRowModel().rows.length;
  const pageIndex = table.getState().pagination.pageIndex;
  const pageSize = table.getState().pagination.pageSize;
  const rangeStart = filteredCount === 0 ? 0 : pageIndex * pageSize + 1;
  const rangeEnd = Math.min((pageIndex + 1) * pageSize, filteredCount);
  const selectedCount = Object.keys(rowSelection).length;

  const statusLabel =
    statusFilter === "all"
      ? "All statuses"
      : statusFilter === "verified"
      ? "Verified"
      : "Needs review";

  return (
    <section aria-labelledby="results-table-heading">
      <h2 id="results-table-heading" className="sr-only">Collection results</h2>

      <div className="mb-3 flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full max-w-[360px] 2xl:max-w-[480px]">
          <label htmlFor="results-search" className="sr-only">Search collection results</label>
          <Search aria-hidden="true" className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#7c899c]" />
          <input
            id="results-search"
            type="text"
            inputMode="search"
            value={globalFilter}
            onChange={(event) => setGlobalFilter(event.target.value)}
            placeholder="Search companies, industry, location…"
            className="h-9 w-full rounded-[7px] border border-[#d6dfe9] bg-white pl-9 pr-9 text-[11px] text-[#172a44] outline-none placeholder:text-[#8b98aa] focus:border-[#6d9ee8] focus:ring-3 focus:ring-[#246bde]/10 2xl:h-10 2xl:text-[13px]"
          />
          {globalFilter && (
            <button
              type="button"
              onClick={() => setGlobalFilter("")}
              className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded text-[#7c899c] hover:bg-[#eef2f7] hover:text-[#10213a]"
              aria-label="Clear results search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {selectedCount > 0 && (
            <span className="mr-1 text-[11px] font-medium text-[#53647c]" aria-live="polite">
              {selectedCount} selected
            </span>
          )}
          <button
            type="button"
            onClick={cycleStatusFilter}
            aria-label={`Status filter: ${statusLabel}. Activate to change.`}
            className={`flex h-9 items-center gap-1.5 rounded-[7px] border px-3 text-[11px] font-semibold transition-colors 2xl:h-10 2xl:px-4 2xl:text-[12px] ${
              statusFilter === "all"
                ? "border-[#d6dfe9] bg-white text-[#53647c] hover:bg-[#f6f8fb]"
                : "border-[#a9c4ef] bg-[#eef4ff] text-[#1f5cb8]"
            }`}
          >
            <Filter className="h-3.5 w-3.5" />
            {statusLabel}
          </button>
          <button
            type="button"
            onClick={toggleColumns}
            aria-pressed={keyColumnsOnly}
            className="flex h-9 items-center gap-1.5 rounded-[7px] border border-[#d6dfe9] bg-white px-3 text-[11px] font-semibold text-[#53647c] transition-colors hover:bg-[#f6f8fb] 2xl:h-10 2xl:px-4 2xl:text-[12px]"
          >
            <Columns3 className="h-3.5 w-3.5" />
            {keyColumnsOnly ? "Show all columns" : "Key columns"}
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] table-fixed text-left text-[11px] 2xl:min-w-[920px] 2xl:text-[13px]">
            <caption className="sr-only">Companies collected with industry, location, evidence, and verification status.</caption>
            <thead className="border-b border-[#dce4ed] bg-[#f6f8fb] text-[#617189]">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} scope="col" className="px-3 py-2.5 font-semibold 2xl:px-4 2xl:py-3" style={{ width: header.getSize() }}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-[#e8edf3]">
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="transition-colors hover:bg-[#f8fafc]">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="truncate px-3 py-2.5 2xl:px-4 2xl:py-3.5">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={table.getVisibleLeafColumns().length} className="px-5 py-10 text-center">
                    <p className="font-semibold text-[#23354f]">No records match these filters.</p>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalFilter("");
                        setStatusFilter("all");
                      }}
                      className="mt-2 text-[11px] font-semibold text-[#246bde] hover:underline"
                    >
                      Clear filters
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-2 text-[11px] text-[#607089] sm:flex-row sm:items-center sm:justify-between 2xl:mt-4 2xl:text-[12px]">
        <div aria-live="polite">Showing {rangeStart}–{rangeEnd} of {filteredCount} results</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#d6dfe9] bg-white text-[#53647c] hover:bg-[#f6f8fb] disabled:opacity-40"
            aria-label="Previous results page"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="min-w-20 text-center font-medium text-[#3e506a]">
            Page {filteredCount === 0 ? 0 : pageIndex + 1} of {table.getPageCount()}
          </span>
          <button
            type="button"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#d6dfe9] bg-white text-[#53647c] hover:bg-[#f6f8fb] disabled:opacity-40"
            aria-label="Next results page"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </section>
  );
}
