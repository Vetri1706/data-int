"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { ArrowLeft, ArrowRight, Loader2, Play } from "lucide-react";
import { WORKFLOW_TEMPLATES } from "@/lib/workflow-templates";
import { runs, executeGroundedSearch, providerLabels, sourceDiscovery, type SourceCandidate, type ModelSelection } from "@/lib/api";
import { ModelSelector } from "@/components/collection/ModelSelector";
import { DagExecutionFeed } from "@/components/collection/DagExecutionFeed";
import { WorkflowStage } from "@/lib/types";

const collectionSchema = z.object({
  prompt: z
    .string()
    .min(5, "Please enter at least 5 characters")
    .max(500, "Maximum 500 characters allowed"),
});

type CollectionFormValues = z.infer<typeof collectionSchema>;

const DEFAULT_PROMPT = "Find potential sponsors for a robotics hackathon in Tamil Nadu.";

const INSPIRATION_CHIPS = [
  {
    label: "Find companies hiring ML engineers",
    prompt: "Find companies in Bengaluru hiring ML engineers with 3+ years experience and salary ranges from official careers portals.",
  },
  {
    label: "List EV suppliers in India",
    prompt: "List EV battery and component suppliers in India with direct catalog links, locations, and certifications.",
  },
  {
    label: "Find research labs in aerospace",
    prompt: "Find premier research labs and university institutes in aerospace engineering in South India.",
  },
  {
    label: "Companies with CSR programs in Tamil Nadu",
    prompt: "Find companies with active CSR programs in Tamil Nadu focused on STEM, robotics, and collegiate hackathons.",
  },
];

const INITIAL_STAGES: WorkflowStage[] = [
  { stage_id: 1, stage_name: "Understand the requirement", status: "pending", duration_ms: null, details: "Define the fields and evidence requirements." },
  { stage_id: 2, stage_name: "Plan the search", status: "pending", duration_ms: null, details: "Generate search queries; refine them when more evidence is needed." },
  { stage_id: 3, stage_name: "Read approved pages", status: "pending", duration_ms: null, details: "Open the selected websites and retrieve their content, respecting access rules." },
  { stage_id: 4, stage_name: "Extract records", status: "pending", duration_ms: null, details: "Use the selected model to read source passages." },
  { stage_id: 5, stage_name: "Validate evidence", status: "pending", duration_ms: null, details: "Verify individual claims and resolve duplicate entities." },
  { stage_id: 6, stage_name: "Save results", status: "pending", duration_ms: null, details: "Persist records with their source citations." },
];
const STAGE_IDS: Record<string, number> = { planning: 1, discovering: 2, collecting: 3, extracting: 4, validating: 5, replanning: 2, finalizing: 6 };

function CreateCollectionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const template = WORKFLOW_TEMPLATES.find(t => t.id === searchParams.get("template"));
  const initialPrompt = searchParams.get("prompt") || template?.prompt || "";
  const [domains, setDomains] = useState(searchParams.get("domains") || "");
  const [permissionConfirmed, setPermissionConfirmed] = useState(false);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const domainFilters = [...new Set(domains.split(/[,\s]+/).map(d => d.trim().toLowerCase().replace(/\.$/, "")).filter(Boolean))];
  const domainError = domainFilters.length > 25 ? "Use at most 25 domain restrictions." : domainFilters.some(d =>
    d.length > 253 || !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/.test(d) || d.split(".").some(label => label.length > 63)
  ) ? "Enter domains such as example.com, without https://, paths or wildcards." : null;
  const [approvedDomains, setApprovedDomains] = useState<string[]>([]);
  const [sourceCandidates, setSourceCandidates] = useState<SourceCandidate[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const discoveryController = useRef<AbortController | null>(null);

  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [isRunning, setIsRunning] = useState(false);
  const [currentStageId, setCurrentStageId] = useState(1);
  const [stages, setStages] = useState<WorkflowStage[]>(INITIAL_STAGES);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modelSelection, setModelSelection] = useState<ModelSelection>({ provider: "local", model: "", allow_external: false });
  const [modelReady, setModelReady] = useState(false);
  const canContinue = !domainError && modelReady && (modelSelection.provider === "local" || modelSelection.allow_external);
  const canRun = canContinue && !isDiscovering && permissionConfirmed && approvedDomains.length > 0;
  const continueReason = domainError || (!modelReady ? "Choose an available processing model to continue." :
    modelSelection.provider !== "local" && !modelSelection.allow_external ? "Allow the selected provider to process this collection, or choose Local Ollama." : null);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<CollectionFormValues>({
    resolver: zodResolver(collectionSchema),
    defaultValues: {
      prompt: initialPrompt || DEFAULT_PROMPT,
    },
  });

  const promptValue = watch("prompt") || "";

  useEffect(() => {
    document.title = "Create collection — Datavault";
    if (initialPrompt) {
      setValue("prompt", initialPrompt);
    }
  }, [initialPrompt, setValue]);

  useEffect(() => () => discoveryController.current?.abort(), []);

  const reviewSources = async (data: CollectionFormValues) => {
    if (!canContinue || isRunning) return;
    discoveryController.current?.abort();
    const controller = new AbortController();
    discoveryController.current = controller;
    setStep(2);
    setErrorMessage(null);
    setDiscoveryError(null);
    setPermissionConfirmed(false);
    setApprovedDomains([]);
    setSourceCandidates([]);
    setIsDiscovering(true);
    const entered = domainFilters.map(domain => ({ domain, pages: [] } as SourceCandidate));
    try {
      const result = await sourceDiscovery.discover(data.prompt, domainFilters, controller.signal);
      if (controller.signal.aborted) return;
      const found = new Map(result.domains.map(candidate => [candidate.domain, candidate]));
      for (const candidate of entered) if (!found.has(candidate.domain)) found.set(candidate.domain, candidate);
      const candidates = [...found.values()];
      setSourceCandidates(candidates);
      setApprovedDomains(candidates.map(candidate => candidate.domain));
    } catch (error) {
      if (controller.signal.aborted) return;
      setDiscoveryError(error instanceof Error && error.name !== "TimeoutError" ? error.message : "Source discovery timed out. Retry or go back and enter a domain you know.");
      setSourceCandidates(entered);
      setApprovedDomains(entered.map(candidate => candidate.domain));
    } finally {
      if (!controller.signal.aborted) setIsDiscovering(false);
    }
  };

  const runCollection = async (data: CollectionFormValues) => {
    if (isRunning || !canRun) return;
    setErrorMessage(null);
    setStep(3);
    setActiveRun(null);
    setIsRunning(true);
    setCurrentStageId(1);
    setStages(INITIAL_STAGES);

    try {
      const response = await executeGroundedSearch(data.prompt, modelSelection, (stage, run) => {
        setCurrentStageId(STAGE_IDS[stage] || 1);
        if (run?.steps) setStages(INITIAL_STAGES.map(item => {
          const observed = run.steps.filter(s => STAGE_IDS[s.step_type] === item.stage_id).at(-1);
          if (!observed) return item;
          const status = ["pending", "running", "completed", "failed", "cancelled"].includes(observed.status)
            ? observed.status as WorkflowStage["status"] : "pending";
          return { ...item, status, duration_ms: observed.duration_ms ?? null };
        }));
      }, { basis: "user_confirmed_permission", approved_domains: approvedDomains, domain_filters: domainFilters }, template?.contract, setActiveRun, sourceCandidates.filter(s => approvedDomains.includes(s.domain)).flatMap(s => s.pages));
      setCurrentStageId(7);
      setStep(4);

      if (response.workflow?.stages?.length > 0) {
        setStages(response.workflow.stages);
      }

      // Navigate to results
      router.push(`/collections/${response.task_id}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "The collection could not be started.";
      setErrorMessage(message);
      setStep(1);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1100px] 2xl:max-w-[1240px]">
      <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-2 text-[11px] text-[#7c899c]">
        <button type="button" onClick={() => router.push("/collections")} className="font-medium hover:text-[#246bde]">
          Collections
        </button>
        <span aria-hidden="true">›</span>
        <span aria-current="page" className="text-[#4d5f78]">New collection</span>
      </nav>

      <div className="mb-7 flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-[24px] font-bold tracking-[-0.035em] text-[#10213a]">Create collection</h1>
          <p className="mt-1 text-[12px] text-[#66758a]">Define the requirement, review it, then run the collection workflow.</p>
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-[11px]" aria-label={`Step ${step} of 4`}>
          <div className="flex items-center gap-1.5">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold ${
                step === 1
                  ? "border-[#246bde] bg-[#246bde] text-white"
                  : step > 1
                  ? "border-[#9ecfb7] bg-[#edf8f2] text-[#238a59]"
                  : "border-[#d7e0e9] bg-white text-[#8190a4]"
              }`}
            >
              1
            </span>
            <span
              className={`font-semibold ${
                step === 1 ? "text-slate-900" : "text-slate-500"
              }`}
            >
              Describe
            </span>
          </div>

          <span className="h-px w-6 shrink-0 bg-[#d8e0e9]" aria-hidden="true" />

          <div className="flex items-center gap-1.5">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold ${
                step === 2
                  ? "border-[#246bde] bg-[#246bde] text-white"
                  : step > 2
                  ? "border-[#9ecfb7] bg-[#edf8f2] text-[#238a59]"
                  : "border-[#d7e0e9] bg-white text-[#8190a4]"
              }`}
            >
              2
            </span>
            <span
              className={`font-medium ${
                step === 2 ? "text-slate-900 font-semibold" : "text-slate-400"
              }`}
            >
              Review
            </span>
          </div>

          <span className="h-px w-6 shrink-0 bg-[#d8e0e9]" aria-hidden="true" />

          <div className="flex items-center gap-1.5">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold ${
                step === 3
                  ? "border-[#246bde] bg-[#246bde] text-white"
                  : step > 3
                  ? "border-[#9ecfb7] bg-[#edf8f2] text-[#238a59]"
                  : "border-[#d7e0e9] bg-white text-[#8190a4]"
              }`}
            >
              3
            </span>
            <span
              className={`font-medium ${
                step === 3 ? "text-slate-900 font-semibold" : "text-slate-400"
              }`}
            >
              Run
            </span>
          </div>

          <span className="h-px w-6 shrink-0 bg-[#d8e0e9]" aria-hidden="true" />

          <div className="flex items-center gap-1.5">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold ${
                step === 4
                  ? "border-[#238a59] bg-[#238a59] text-white"
                  : "border-[#d7e0e9] bg-white text-[#8190a4]"
              }`}
            >
              4
            </span>
            <span
              className={`font-medium ${
                step === 4 ? "text-emerald-700 font-semibold" : "text-slate-400"
              }`}
            >
              Results
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-[12px] border border-[#dde5ee] bg-white p-5 sm:p-7 lg:p-9">
        {isRunning ? (
          <div className="py-5 text-center" aria-live="polite">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-[#eaf2ff] text-[#246bde]">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
            <h2 className="mt-4 text-[18px] font-semibold text-[#10213a]">Running the collection workflow</h2>
            <p className="mx-auto mt-1 max-w-[620px] text-[12px] leading-5 text-[#66758a]">
              {providerLabels[modelSelection.provider]} · {modelSelection.model}
              <br />Progress follows the server. Model calls and workflows have bounded time limits.
            </p>

            <DagExecutionFeed currentStageId={currentStageId} stages={stages} />
            {activeRun && <button type="button" className="mt-5 rounded border px-4 py-2" onClick={async () => {
              try { await runs.cancel(activeRun); } catch (e) { setErrorMessage(e instanceof Error ? e.message : "Cancellation failed"); }
            }}>Cancel run</button>}
            {errorMessage && <p role="alert">{errorMessage}</p>}
          </div>
        ) : step === 2 ? (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Review requirement</div>
            <h2 className="mt-2 text-[22px] font-bold tracking-[-0.025em] text-[#10213a]">Choose sources to read</h2>
            <p className="mt-1 text-[13px] text-[#68778c]">These are search listings. We have not read these pages yet. Your approval lets the next step open the selected websites and collect evidence.</p>

            <div className="mt-6 rounded-[9px] border border-[#dce4ed] bg-[#f7f9fc] p-4">
              <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7b899c]">Collection requirement</div>
              <p className="mt-2 text-[14px] leading-6 text-[#23354f]">{promptValue}</p>
              {domainFilters.length > 0 && <p className="mt-3 text-sm">Search restricted to: {domainFilters.join(", ")}</p>}
              {template && <div className="mt-3 text-sm"><p>Template: {template.name} - target {template.contract.target_count}</p>
                <ul>{template.contract.fields?.map(f => <li key={f.name}>{f.name} ({f.field_type}){f.required ? " - required" : " - optional"}</li>)}</ul></div>}
              <p className="mt-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--muted)]">Processing: {providerLabels[modelSelection.provider]} · {modelSelection.model}</p>
              {modelSelection.provider !== "local" && <p className="mt-1 text-xs text-[var(--muted)]">You allowed {providerLabels[modelSelection.provider]} to process this collection&apos;s prompt, fields, queries, and web passages.</p>}
            </div>

            <section className="mt-6" aria-label="Source review" aria-busy={isDiscovering}>
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold">Candidate source domains</h3>
                <button type="button" disabled={isDiscovering} onClick={handleSubmit(reviewSources)} className="rounded px-2 py-2 text-xs font-semibold text-[#246bde] disabled:opacity-50">Find sources again</button>
              </div>
              <p className="mt-1 text-xs leading-5 text-[#68778c]">Titles and descriptions come from search engines. Select the websites this run may read; their claims will be checked after retrieval.</p>
              {isDiscovering && <p role="status" className="mt-4 flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Finding candidate sources...</p>}
              {discoveryError && <p role="alert" className="mt-3 rounded border border-[#efd2d6] bg-[#fff7f8] p-3 text-sm text-[#a63c47]">{discoveryError}</p>}
              {!isDiscovering && sourceCandidates.length === 0 && <p role="status" className="mt-4 rounded border p-4 text-sm">No candidate domains were returned. Retry discovery, or go back to revise the prompt or enter a domain you know.</p>}
              <div className="mt-3 max-h-80 space-y-2 overflow-y-auto">
                {sourceCandidates.map(candidate => <div key={candidate.domain} className="rounded-lg border border-[#dce4ed] p-3">
                  <label className="flex cursor-pointer items-center gap-3 text-sm font-semibold">
                    <input type="checkbox" checked={approvedDomains.includes(candidate.domain)} onChange={event => {
                      setPermissionConfirmed(false);
                      setApprovedDomains(current => event.target.checked ? [...current, candidate.domain] : current.filter(domain => domain !== candidate.domain));
                    }} />
                    {candidate.domain}
                  </label>
                  {candidate.pages.length ? <ul className="ml-7 mt-2 space-y-1 text-xs">
                    {candidate.pages.slice(0, 3).map(page => <li key={page.url}><a className="break-words text-[#246bde] underline" href={page.url} target="_blank" rel="noreferrer">{page.title || page.url}</a><span className="ml-2 text-[#68778c]">{page.provider}</span>{page.snippet && <p className="mt-1 line-clamp-3 text-[#68778c]">{page.snippet}</p>}</li>)}
                  </ul> : <p className="ml-7 mt-2 text-xs text-[#68778c]">Entered by you; no search result page was returned for this domain.</p>}
                </div>)}
              </div>
              {!isDiscovering && sourceCandidates.length > 0 && <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-lg bg-[#f7f9fc] p-4 text-sm">
                <input type="checkbox" className="mt-1" checked={permissionConfirmed} disabled={!approvedDomains.length} onChange={event => setPermissionConfirmed(event.target.checked)} />
                I have permission to collect from the selected domains. Collection will respect robots rules and stop at access restrictions.
              </label>}
              {!canRun && !isDiscovering && sourceCandidates.length > 0 && <p className="mt-2 text-xs text-[#68778c]" role="status">{!approvedDomains.length ? "Select at least one source domain to collect from." : "Confirm permission for the selected domains to run collection."}</p>}
            </section>

            <div className="mt-8 flex items-center justify-between border-t border-[#edf1f5] pt-5">
              <button
                type="button"
                onClick={() => { discoveryController.current?.abort(); setIsDiscovering(false); setStep(1); }}
                className="flex h-10 items-center gap-2 rounded-[7px] border border-[#d5dee8] px-4 text-[12px] font-semibold text-[#53647c] hover:bg-[#f5f7fa] hover:text-[#10213a]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back
              </button>
              <button
                type="button"
                onClick={handleSubmit(runCollection)}
                disabled={!canRun || isRunning}
                className="flex h-10 items-center gap-2 rounded-[7px] bg-[#17345f] px-5 text-[12px] font-semibold text-white hover:bg-[#102b50] disabled:cursor-not-allowed disabled:opacity-45"
              >
                <Play className="h-3.5 w-3.5" />
                Run collection
              </button>
            </div>
          </div>
        ) : (
          <div>
            <h2 className="text-[22px] font-bold tracking-[-0.025em] text-[#10213a]">
              What are you looking for?
            </h2>
            <p className="mt-1 text-[13px] text-[#68778c]">
              Describe your requirement in a few words. We&apos;ll take care of the rest.
            </p>

            <form onSubmit={handleSubmit(reviewSources)} noValidate className="mt-6">
              <div className="relative">
                <label htmlFor="collection-requirement" className="sr-only">Collection requirement</label>
                <textarea
                  id="collection-requirement"
                  {...register("prompt")}
                  defaultValue={initialPrompt || DEFAULT_PROMPT}
                  rows={4}
                  maxLength={500}
                  aria-invalid={errors.prompt ? "true" : "false"}
                  aria-describedby={errors.prompt ? "collection-requirement-error" : undefined}
                  placeholder="e.g. Find companies that have sponsored technical events in the last two years."
                  className="min-h-32 w-full resize-none rounded-[9px] border border-[#cfd9e5] bg-white p-4 pb-9 text-[13px] leading-6 text-[#172a44] outline-none transition-colors placeholder:text-[#8b98aa] focus:border-[#6d9ee8] focus:ring-3 focus:ring-[#246bde]/10"
                />
                <div className="absolute bottom-3 right-3 font-mono text-[10px] text-[#8592a4]">
                  {promptValue.length}/500
                </div>
              </div>
              {errors.prompt && (
                <p id="collection-requirement-error" role="alert" className="mt-1.5 text-xs text-[#c64b57]">
                  {errors.prompt.message}
                </p>
              )}
              {errorMessage && (
                <div role="alert" className="mt-3 rounded-[7px] border border-[#efd2d6] bg-[#fff7f8] px-3 py-2 text-xs text-[#a63c47]">{errorMessage}{activeRun && <Link className="ml-2 underline" href={`/runs/${activeRun}`}>Inspect run</Link>}</div>
              )}

              <div className="mt-5 space-y-2 text-sm">
                <label htmlFor="approved-domains" className="block font-semibold">Limit search to domains (optional)</label>
                <input id="approved-domains" value={domains} onChange={e => setDomains(e.target.value)} placeholder="Leave blank to discover sources automatically" aria-invalid={Boolean(domainError)} aria-describedby="domain-help" className="w-full rounded border p-3" />
                <p id="domain-help" className="text-xs text-[#68778c]">Leave this blank if you don&apos;t know the websites yet. Continue will find candidate sources for you to review.</p>
                {domainError && <p role="alert" className="text-xs text-[#a63c47]">{domainError}</p>}
              </div>
              <ModelSelector value={modelSelection} onChange={setModelSelection} onReadyChange={setModelReady} preferredProvider={searchParams.get("local") === "1" ? "local" : undefined} />

              <div className="mt-6 rounded-[9px] bg-[#f7f9fc] p-4">
                <span className="block text-[11px] font-semibold text-[#23354f]">
                  Need inspiration?
                </span>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {INSPIRATION_CHIPS.map((chip) => (
                    <button
                      key={chip.label}
                      type="button"
                      onClick={() => setValue("prompt", chip.prompt)}
                      className="rounded-full border border-[#d7e0ea] bg-white px-3 py-1.5 text-[11px] font-medium text-[#55657d] transition-colors hover:border-[#aebdd0] hover:text-[#10213a]"
                    >
                      {chip.label}
                    </button>
                  ))}
                </div>
              </div>

              {continueReason && <p id="continue-reason" role="status" className="mt-5 text-xs text-[#68778c]">{continueReason}</p>}
              <div className="mt-8 flex items-center justify-between border-t border-[#edf1f5] pt-5">
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="h-10 rounded-[7px] border border-[#d5dee8] px-4 text-[12px] font-semibold text-[#53647c] transition-colors hover:bg-[#f5f7fa] hover:text-[#10213a]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!canContinue}
                  aria-describedby={continueReason ? "continue-reason" : undefined}
                  className="flex h-10 items-center gap-2 rounded-[7px] bg-[#17345f] px-5 text-[12px] font-semibold text-white transition-colors hover:bg-[#102b50] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <span>Continue</span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

export default function CreateCollectionPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-slate-400">Loading wizard...</div>}>
      <CreateCollectionContent />
    </Suspense>
  );
}
