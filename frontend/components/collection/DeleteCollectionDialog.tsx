"use client";

import React, { useEffect, useRef } from "react";
import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";

interface DeleteCollectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  title: string;
  count?: number;
  isBulk?: boolean;
}

export function DeleteCollectionDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  count,
  isBulk = false,
}: DeleteCollectionDialogProps) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setLoading(false);
    const timer = setTimeout(() => cancelButtonRef.current?.focus(), 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, loading, onClose]);

  if (!isOpen) return null;

  const handleDelete = async () => {
    try {
      setLoading(true);
      setError(null);
      await onConfirm();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete collection.");
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#10213a]/45 p-4 backdrop-blur-[2px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !loading) onClose();
      }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
        className="w-full max-w-[440px] rounded-[10px] border border-[#e2c3c8] bg-white p-5 shadow-[0_16px_36px_rgba(20,35,60,0.18)] sm:p-6"
      >
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#fcedef] text-[#c64b57]">
            <Trash2 className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              id="delete-dialog-title"
              className="text-[16px] font-bold tracking-[-0.02em] text-[#10213a]"
            >
              {isBulk ? `Delete ${count ?? ""} Collections` : "Delete Collection"}
            </h2>
            <p
              id="delete-dialog-description"
              className="mt-2 text-[12px] leading-5 text-[#5e7088]"
            >
              Are you sure you want to delete{" "}
              <strong className="font-semibold text-[#1a2c47]">
                {isBulk ? `${count} selected collections` : `“${title}”`}
              </strong>
              ? All associated datasets, extracted records, and source citations will be permanently removed.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            aria-label="Close dialog"
            className="rounded p-1 text-[#7c8b9e] hover:bg-[#f1f4f8] hover:text-[#10213a] disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-3 flex items-center gap-2 rounded-[6px] border border-[#f3c8ce] bg-[#fff5f6] p-2.5 text-[11px] font-medium text-[#b33444]"
          >
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2.5 border-t border-[#edf2f7] pt-4">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-[7px] border border-[#d6dfe9] bg-white px-3.5 py-2 text-[11px] font-semibold text-[#53647c] hover:bg-[#f6f8fb] hover:text-[#10213a] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-[7px] bg-[#c64b57] px-4 py-2 text-[11px] font-semibold text-white shadow-sm hover:bg-[#b03d48] active:bg-[#9a343e] disabled:opacity-60"
          >
            {loading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Deleting…</span>
              </>
            ) : (
              <>
                <Trash2 className="h-3.5 w-3.5" />
                <span>Delete permanently</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
