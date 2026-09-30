"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { WORKFLOW_TEMPLATES } from "@/lib/workflow-templates";

export default function WorkflowsPage() {
  useEffect(() => {
    document.title = "Workflows — Datavault";
  }, []);

  return (
    <div className="mx-auto w-full max-w-[1400px] 2xl:max-w-[1680px]">
      <header className="mb-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Collection methods</div>
        <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">Workflows</h1>
        <p className="mt-1 text-[12px] text-[#66758a]">Reusable source, extraction, and verification patterns.</p>
      </header>

      <section className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white" aria-labelledby="workflow-list-heading">
        <h2 id="workflow-list-heading" className="sr-only">Workflow templates</h2>
        <ol className="divide-y divide-[#e8edf3]">
          {WORKFLOW_TEMPLATES.map((workflow, index) => (
            <li key={workflow.id} className="grid gap-4 px-4 py-4 hover:bg-[#f8fafc] sm:grid-cols-[36px_1fr_auto] sm:items-center sm:px-5">
              <span className="font-mono text-[11px] font-semibold text-[#7c899c]">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[13px] font-semibold text-[#172a44]">{workflow.name}</h3>
                  <span className="rounded-full bg-[#eef2f7] px-2 py-0.5 text-[9px] font-semibold text-[#607089]">{workflow.category}</span>
                </div>
                <p className="mt-1 max-w-[650px] text-[11px] leading-5 text-[#66758a]">{workflow.description}</p>
                <p className="mt-1.5 font-mono text-[9px] text-[#7c899c]">{workflow.contract.fields?.length} fields - target {workflow.contract.target_count} accepted records</p>
              </div>
              <Link href={`/collections/new?template=${workflow.id}`} className="flex h-8 items-center gap-1.5 justify-self-start rounded-[6px] border border-[#d6dfe9] bg-white px-3 text-[10px] font-semibold text-[#53647c] hover:bg-[#f3f6f9] hover:text-[#17345f] sm:justify-self-end">
                Use workflow <ArrowRight className="h-3 w-3" />
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
