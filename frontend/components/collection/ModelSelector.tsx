"use client";

import { useEffect, useId, useRef, useState } from "react";
import { models, providerLabels, type ModelCatalog, type ModelSelection } from "@/lib/api";

const control = "mt-2 h-11 w-full min-w-0 cursor-pointer rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] px-3 text-sm text-[var(--foreground)] outline-none hover:border-[var(--muted)] focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:cursor-not-allowed disabled:opacity-60";
const costOrder = { free: 0, local: 0, free_tier: 1, credits: 2, paid: 3, unknown: 4 };
const sortModels = (items: ModelCatalog["providers"][number]["models"]) => [...items].sort((a, b) =>
  costOrder[a.cost?.kind ?? "unknown"] - costOrder[b.cost?.kind ?? "unknown"] ||
  Number(b.available) - Number(a.available) || a.id.localeCompare(b.id));

// Native selects are intentional: OS-owned popup, typeahead and keyboard behavior.
export function ModelSelector({ value, onChange, onReadyChange, preferredProvider }: {
  value: ModelSelection;
  onChange: (value: ModelSelection) => void;
  onReadyChange: (ready: boolean) => void;
  preferredProvider?: ModelSelection["provider"];
}) {
  const id = useId();
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const initialSelection = useRef(value);
  const initialized = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    models.list(controller.signal).then((data) => {
      if (!controller.signal.aborted) {
        setCatalog(data); setLoading(false);
        if (!initialized.current) {
          const current = initialSelection.current;
          // Only an empty initial choice may take the server default. Returning
          // from review/failure must preserve even a now-unavailable user choice.
          if (!current.model) {
            const preferred = data.providers.find((item) => item.id === preferredProvider && item.available);
            if (preferred?.default_model) onChange({ provider: preferred.id, model: preferred.default_model, allow_external: false });
            else if (!preferredProvider && data.default) onChange({ ...data.default, allow_external: false });
          }
          initialized.current = true;
        }
      }
    }).catch((err) => {
      if (!controller.signal.aborted) { setError(err instanceof Error ? err.message : "Cannot load models."); setLoading(false); }
    });
    return () => controller.abort();
  }, [attempt, onChange, preferredProvider]);

  const provider = catalog?.providers.find((item) => item.id === value.provider);
  const model = provider?.models.find((item) => item.id === value.model);
  const available = Boolean(!loading && !error && provider?.available && model?.available);
  const usableCount = provider?.models.filter((item) => item.available).length ?? 0;
  const sortedModels = sortModels(provider?.models ?? []);
  const refresh = () => { setError(null); setLoading(true); setAttempt((current) => current + 1); };
  useEffect(() => { onReadyChange(available); }, [available, onReadyChange]);

  return (
    <fieldset className="mt-6 border-t border-[var(--border)] pt-5" aria-describedby={`${id}-help`} aria-busy={loading}>
      <legend className="px-1 text-sm font-semibold text-[var(--foreground)]">Processing model</legend>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="min-w-0 text-xs font-medium text-[var(--muted)]">
          <label htmlFor={`${id}-provider`}>Provider</label>
          <select id={`${id}-provider`} className={control} value={value.provider} disabled={loading || !catalog} onChange={(event) => {
            const next = catalog?.providers.find((item) => item.id === event.target.value);
            if (next) onChange({ provider: next.id, model: next.models.find((item) => item.id === next.default_model && item.available)?.id || sortModels(next.models).find((item) => item.available)?.id || "", allow_external: false });
          }}>
            {!catalog ? <option value="local">Loading providers…</option> : catalog.providers.map((item) => (
              <option key={item.id} value={item.id} disabled={!item.available}>{item.label}{!item.available ? " · unavailable" : ""}</option>
            ))}
          </select>
        </div>
        <div className="min-w-0 text-xs font-medium text-[var(--muted)]">
          <label htmlFor={`${id}-model`}>Model</label>
          <select id={`${id}-model`} className={control} value={value.model} disabled={loading || !provider?.available} onChange={(event) => onChange({ ...value, model: event.target.value, allow_external: false })}>
            {!provider ? <option value={value.model}>Loading models…</option> : <>
              {!model && <option value={value.model} disabled>{provider.models.length ? `${value.model || "Choose a model"} · unavailable` : "No models available"}</option>}
              {sortedModels.map((item) => (
                <option key={item.id} value={item.id} disabled={!item.available} title={item.reason ?? item.cost?.note}>{item.label}{item.cost ? ` · ${item.cost.label}` : ""}{!item.available ? " · unavailable" : ""}</option>
              ))}
            </>}
          </select>
        </div>
      </div>
      <div className="mt-1 flex min-h-11 flex-wrap items-center justify-between gap-x-3 text-xs text-[var(--muted)]">
        <span aria-live="polite">{loading ? "Checking available models…" : provider ? `${provider.models.length} ${value.provider === "local" ? "installed models" : "models in catalog"} · ${usableCount} for collections` : "Model catalog unavailable"}</span>
        <button type="button" className="min-h-11 shrink-0 rounded px-1 font-semibold text-[var(--primary)] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-[var(--focus)] disabled:cursor-wait disabled:opacity-60" disabled={loading} onClick={refresh}>
          {error ? "Retry models" : "Refresh models"}
        </button>
      </div>
      <div className="min-h-10 text-xs leading-5 text-[var(--muted)]" id={`${id}-help`} aria-live="polite">
        {error ? <div role="alert">{error}</div>
          : loading ? "Fetching model names only. Your collection inputs are not sent."
          : !available ? model?.reason || provider?.reason || "This model is unavailable. Choose another model to continue."
          : value.provider === "local" ? "Model processing stays on the server running Ollama. Web searches still contact search engines and source websites."
          : `${providerLabels[value.provider]}${value.provider === "huggingface" || value.provider === "openrouter" ? " and its selected inference provider" : ""} receives the collection prompt, requested fields, search queries, and retrieved web passages. Your API key stays on the server.`}
        {model?.cost && <p className="mt-2"><strong>{model.cost.label}.</strong> {model.cost.note} <a className="underline" href={model.cost.source_url} target="_blank" rel="noreferrer">Provider pricing</a></p>}
        {model?.context_length && <p>Context: {model.context_length.toLocaleString()} tokens.</p>}
        {model?.catalog_source === "documented" && <p>Listed from provider documentation; omitted by its model-list API.</p>}
        {provider && <p className="mt-1">Free models appear first, followed by free tiers, credits and paid models. Catalog access does not verify inference quota.</p>}
        {provider && usableCount < provider.models.length && <p>Models incompatible with this text workflow and cloud-relayed Ollama models cannot be selected.</p>}
        {catalog?.providers.some((item) => !item.available) && <details className="mt-2">
          <summary className="cursor-pointer">Unavailable providers</summary>
          {catalog.providers.filter((item) => !item.available).map((item) => <p key={item.id}>{item.label}: {item.reason}</p>)}
        </details>}
      </div>
      {value.provider !== "local" && (
        <label className="mt-2 flex min-h-11 cursor-pointer items-start gap-3 rounded-lg bg-[var(--surface-subtle)] p-3 text-xs leading-5 text-[var(--foreground)]">
          <input type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-[var(--primary)]" checked={value.allow_external} onChange={(event) => onChange({ ...value, allow_external: event.target.checked })} />
          Allow {providerLabels[value.provider]} to process these inputs for this collection.
        </label>
      )}
    </fieldset>
  );
}
