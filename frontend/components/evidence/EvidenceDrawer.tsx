"use client";

import React, { useEffect, useRef } from "react";
import { ExternalLink, ShieldCheck, X } from "lucide-react";
import { EntityRecord } from "@/lib/types";

interface EvidenceDrawerProps {
  entity: EntityRecord | null;
  onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function EvidenceDrawer({ entity, onClose }: EvidenceDrawerProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!entity) return;

    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [entity, onClose]);

  if (!entity) return null;


  const sources = entity.provenance?.source_urls ?? [];
  const httpStatus = entity.provenance?.http_status;
  const linkChecked = typeof httpStatus === "number";

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-[#10213a]/35"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        className="flex h-full w-full max-w-[520px] flex-col border-l border-[#d4dde8] bg-white shadow-[-18px_0_40px_rgba(25,43,70,0.12)]"
      >
        <div className="flex items-start justify-between border-b border-[#e5ebf1] px-5 py-4 sm:px-6">
          <div>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#41658e]">
              <ShieldCheck className="h-3.5 w-3.5" />
              Evidence record
            </div>
            <h2 id="evidence-drawer-title" className="mt-1.5 text-[19px] font-bold tracking-[-0.02em] text-[#10213a]">
              {entity.canonical_name}
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-[6px] text-[#718096] hover:bg-[#f0f3f7] hover:text-[#10213a]"
            aria-label="Close evidence drawer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto px-5 py-5 sm:px-6">
          <section aria-labelledby="confidence-heading" className="border-b border-[#e8edf3] pb-6">
            <h3 id="confidence-heading" className="text-sm font-semibold">Claim verification</h3>
            <p className="mt-2 text-sm">{entity.verification ? `${entity.verification.accepted ? "Accepted" : "Needs review"} - ${Math.round(entity.verification.field_coverage * 100)}% of requested fields supported` : "Legacy record: typed verification unavailable"}</p>
            <p className="mt-2 text-xs text-slate-600">{linkChecked ? `Retrieved with HTTP ${httpStatus}` : "Retrieval status unknown"}. No probability of correctness is assigned.</p>
            <dl className="mt-3 space-y-3">
              {Object.entries(entity.claims ?? {}).map(([name, claim]) => <div key={name} className="rounded border p-3 text-xs">
                <dt className="font-semibold">{name}: {claim.state}</dt>
                <dd className="mt-1">{claim.value === null ? "No value found" : JSON.stringify(claim.value)}</dd>
                <dd className="mt-1 text-slate-600">{claim.reason}</dd>
                {claim.evidence?.map((e, i) => <blockquote key={i} className="mt-2 border-l-2 pl-2">{e.verbatim_quote} <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-700">Source</a></blockquote>)}
              </div>)}
            </dl>
            {entity.verification?.acceptance_failures.map((failure, i) => <p key={i} className="mt-2 text-xs text-amber-800">{failure.field}: {failure.reason}</p>)}
          </section>

          {/* Extracted Business Attributes */}
          {entity.primary_attributes && Object.keys(entity.primary_attributes).length > 0 && (
            <section aria-labelledby="attributes-heading" className="border-b border-[#e8edf3] pb-6">
              <h3 id="attributes-heading" className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#718096]">
                Extracted Attributes
              </h3>
              <dl className="mt-3 divide-y divide-[#edf1f5] rounded-[7px] border border-[#e5ebf1] bg-[#f8fafc] px-3.5 text-[11px]">
                {Object.entries(entity.primary_attributes).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between py-2.5">
                    <dt className="font-medium capitalize text-[#53647c]">{key.replace(/[_\s]+/g, " ")}</dt>
                    <dd className="max-w-[280px] truncate font-semibold text-[#172a44]" title={String(value)}>
                      {String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section aria-labelledby="field-evidence-heading">
            <h3 id="field-evidence-heading" className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#718096]">Field evidence</h3>
            <div className="mt-3 divide-y divide-[#e8edf3] border-y border-[#e8edf3]">
              {entity.provenance?.field_evidence?.length ? (
                entity.provenance.field_evidence.map((evidence, index) => (
                  <article key={`${evidence.field_name}-${index}`} className="py-4 text-[11px]">
                    <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-[#246bde]">{evidence.field_name}</div>
                    <blockquote className="mt-2 border-l-2 border-[#a8c5ef] pl-3 leading-5 text-[#41526a]">“{evidence.verbatim_quote}”</blockquote>
                    {evidence.char_start !== undefined && <p className="mt-1 font-mono text-[10px] text-[#718096]">Source text characters {evidence.char_start}–{evidence.char_end}</p>}
                    <a
                      href={evidence.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2.5 flex items-center gap-1.5 font-medium text-[#246bde] hover:underline"
                    >
                      <span className="max-w-[360px] truncate">{evidence.source_url}</span>
                      <ExternalLink className="h-3 w-3 shrink-0" />
                    </a>
                  </article>
                ))
              ) : (
                <p className="py-5 text-[11px] leading-5 text-[#607089]">No field-level evidence was recorded for this entity.</p>
              )}
            </div>
          </section>

          <section aria-labelledby="sources-heading">
            <h3 id="sources-heading" className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#718096]">Corroborating sources ({sources.length})</h3>
            <ul className="mt-2 divide-y divide-[#e8edf3] border-y border-[#e8edf3]">
              {sources.map((url, index) => (
                <li key={`${url}-${index}`}>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between gap-3 py-3 text-[11px] font-medium text-[#246bde] hover:underline"
                  >
                    <span className="truncate">{url}</span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-[#718096]" />
                  </a>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
