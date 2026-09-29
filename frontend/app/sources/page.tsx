"use client";

import React, { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { sources, type Source } from "@/lib/api";


export default function SourcesPage() {
  const [rows, setRows] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    document.title = "Sources — Datavault";
    let active = true;
    sources.list().then(({ data }) => { if (active) setRows(data); })
      .catch((error: Error) => { if (active) setError(error.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none">
      <header className="mb-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Evidence network</div>
        <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">Sources</h1>
        <p className="mt-1 text-[12px] text-[#66758a]">Registered domains and their last recorded retrieval status.</p>
      </header>

      {error && <p role="alert" className="mb-4 text-sm text-[#9b3543]">Could not load sources: {error}</p>}
      <section aria-labelledby="sources-table-heading" className="overflow-hidden rounded-[9px] border border-[#dce4ed] bg-white">
        <h2 id="sources-table-heading" className="sr-only">Source registry</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-[11px]">
            <caption className="sr-only">Registered domains, configured trust tiers, and last recorded retrieval checks.</caption>
            <thead className="border-b border-[#dce4ed] bg-[#f6f8fb] text-[#617189]">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-semibold">Domain</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Publisher</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Category</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Registry tier</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Last checked</th>
                <th scope="col" className="px-4 py-2.5 font-semibold">Health</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e8edf3]">
              {loading && <tr><td colSpan={6} className="p-6 text-[#607089]">Loading sources…</td></tr>}
              {!loading && !error && !rows.length && <tr><td colSpan={6} className="p-6 text-[#607089]">No sources have been recorded yet.</td></tr>}
              {rows.map((src) => (
                <tr key={src.domain} className="hover:bg-[#f8fafc]">
                  <td className="px-4 py-3 font-medium text-[#246bde]">
                    <a
                      href={`https://${src.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 hover:underline"
                    >
                      <span>{src.domain}</span>
                      <ExternalLink className="h-3 w-3 text-[#7c899c]" />
                    </a>
                  </td>
                  <td className="px-3 py-3 font-medium text-[#23354f]">
                    {src.display_name ?? src.domain}
                  </td>
                  <td className="px-3 py-3 text-[#607089]">
                    {src.source_type}
                  </td>
                  <td className="px-3 py-3 font-mono font-semibold text-[#23354f]">
                    {src.trust_tier ?? "Unassigned"}
                  </td>
                  <td className="px-3 py-3 font-medium text-[#53647c]">
                    {src.last_checked_at ? new Date(src.last_checked_at).toLocaleString() : "Never"}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1.5 font-mono font-semibold text-[#53647c]">
                      <span className="h-1.5 w-1.5 rounded-full bg-[#8290a3]" aria-hidden="true" />
                      {src.last_status_code ? `HTTP ${src.last_status_code}` : "Not checked"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
