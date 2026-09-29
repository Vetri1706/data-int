"use client";

import React, { useEffect, useState } from "react";
import { Check } from "lucide-react";

type ExportFormat = "CSV" | "JSON" | "XLSX";

export default function SettingsPage() {
  const [format, setFormat] = useState<ExportFormat>("CSV");
  const [officialSources, setOfficialSources] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    document.title = "Settings — Datavault";
    let mounted = true;
    Promise.resolve().then(() => {
      if (!mounted) return;
      try {
        const stored = window.localStorage.getItem("datavault-settings");
        if (stored) {
          const parsed = JSON.parse(stored) as { format?: ExportFormat; officialSources?: boolean };
          if (parsed.format) setFormat(parsed.format);
          if (typeof parsed.officialSources === "boolean") setOfficialSources(parsed.officialSources);
        }
      } catch {
        // Keep the documented defaults when local preferences are unavailable.
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  const save = () => {
    try {
      window.localStorage.setItem(
        "datavault-settings",
        JSON.stringify({ format, officialSources })
      );
    } catch {
      // The in-memory setting still applies for this session.
    }
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2400);
  };

  return (
    <div className="mx-auto w-full max-w-[1100px] 2xl:max-w-[1280px]">
      <header className="mb-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Workspace</div>
        <h1 className="mt-1.5 text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">Settings</h1>
        <p className="mt-1 text-[12px] text-[#66758a]">Set practical defaults for new collections and exports.</p>
      </header>

      <section className="rounded-[9px] border border-[#dce4ed] bg-white" aria-labelledby="collection-defaults-heading">
        <div className="border-b border-[#e5ebf1] px-5 py-4 sm:px-6">
          <h2 id="collection-defaults-heading" className="text-[14px] font-bold text-[#10213a]">Collection defaults</h2>
          <p className="mt-1 text-[11px] text-[#66758a]">These settings apply when a new collection does not specify an override.</p>
        </div>

        <div className="divide-y divide-[#e8edf3] px-5 sm:px-6">
          <div className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-[12px] font-semibold text-[#23354f]">Prefer official sources</div>
              <p className="mt-1 text-[11px] text-[#718096]">Rank first-party company, regulatory, and institutional sources above aggregators.</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={officialSources}
              onClick={() => setOfficialSources((current) => !current)}
              className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors ${officialSources ? "border-[#246bde] bg-[#246bde]" : "border-[#bac6d3] bg-[#d7dee7]"}`}
            >
              <span className={`absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow-sm transition-transform ${officialSources ? "left-[21px]" : "left-0.5"}`} />
              <span className="sr-only">Prefer official sources</span>
            </button>
          </div>

          <fieldset className="flex flex-col gap-3 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <legend className="text-[12px] font-semibold text-[#23354f]">Default export format</legend>
              <p className="mt-1 text-[11px] text-[#718096]">Used as the first option in collection export menus.</p>
            </div>
            <div className="inline-flex self-start rounded-[7px] border border-[#d6dfe9] bg-[#f6f8fb] p-0.5" role="radiogroup" aria-label="Default export format">
              {(["CSV", "JSON", "XLSX"] as ExportFormat[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={format === option}
                  onClick={() => setFormat(option)}
                  className={`rounded-[5px] px-3 py-1.5 text-[10px] font-semibold ${format === option ? "bg-white text-[#174e9f] shadow-[0_1px_2px_rgba(27,48,75,0.08)]" : "text-[#66758a] hover:text-[#23354f]"}`}
                >
                  {option}
                </button>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-[#e5ebf1] px-5 py-4 sm:px-6">
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-[#197248]" aria-live="polite">
            {saved && <><Check className="h-3.5 w-3.5" /> Preferences saved</>}
          </span>
          <button type="button" onClick={save} className="h-9 rounded-[7px] bg-[#17345f] px-4 text-[11px] font-semibold text-white hover:bg-[#102b50]">
            Save changes
          </button>
        </div>
      </section>
    </div>
  );
}
