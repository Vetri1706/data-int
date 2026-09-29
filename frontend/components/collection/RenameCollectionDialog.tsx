"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Edit3, Loader2, X } from "lucide-react";

interface RenameCollectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (newTitle: string) => Promise<void>;
  initialTitle: string;
}

export function RenameCollectionDialog({
  isOpen,
  onClose,
  onSave,
  initialTitle,
}: RenameCollectionDialogProps) {
  const [title, setTitle] = useState(initialTitle);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setTitle(initialTitle);
    setError(null);
    setLoading(false);
    const timer = setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 50);

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
  }, [isOpen, initialTitle, loading, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setError("Collection title cannot be empty.");
      return;
    }
    if (trimmed === initialTitle.trim()) {
      onClose();
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await onSave(trimmed);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to rename collection.");
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
        aria-labelledby="rename-dialog-title"
        className="w-full max-w-[460px] rounded-[10px] border border-[#d6dfe9] bg-white p-5 shadow-[0_16px_36px_rgba(20,35,60,0.18)] sm:p-6"
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#41658e]">
            <Edit3 className="h-3.5 w-3.5" />
            Manage Collection
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

        <h2
          id="rename-dialog-title"
          className="mt-2 text-[17px] font-bold tracking-[-0.02em] text-[#10213a]"
        >
          Rename Collection
        </h2>

        <form onSubmit={handleSubmit} className="mt-4">
          <div>
            <label
              htmlFor="collection-name-input"
              className="block text-[11px] font-medium text-[#53647c]"
            >
              Collection Title
            </label>
            <input
              ref={inputRef}
              id="collection-name-input"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={loading}
              placeholder="e.g. South India AI Startups"
              className="mt-1.5 h-10 w-full rounded-[7px] border border-[#d6dfe9] bg-white px-3 text-[13px] text-[#172a44] outline-none transition-colors placeholder:text-[#8b98aa] focus:border-[#6d9ee8] focus:ring-3 focus:ring-[#246bde]/10 disabled:bg-[#f8fafc]"
            />
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
              type="button"
              onClick={onClose}
              disabled={loading}
              className="rounded-[7px] border border-[#d6dfe9] bg-white px-3.5 py-2 text-[11px] font-semibold text-[#53647c] hover:bg-[#f6f8fb] hover:text-[#10213a] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !title.trim()}
              className="inline-flex items-center gap-1.5 rounded-[7px] bg-[#246bde] px-4 py-2 text-[11px] font-semibold text-white shadow-sm hover:bg-[#1959c2] active:bg-[#154ca5] disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Saving…</span>
                </>
              ) : (
                <span>Save changes</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
