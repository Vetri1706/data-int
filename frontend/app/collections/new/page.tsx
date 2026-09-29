"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { ArrowLeft, ArrowRight, Loader2, Play } from "lucide-react";
import { executeGroundedSearch, type ModelSelection } from "@/lib/api";
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
  { stage_id: 1, stage_name: "Understand the requirement", status: "pending", duration_ms: 0, details: "Define the fields and evidence requirements." },
  { stage_id: 2, stage_name: "Plan the search", status: "pending", duration_ms: 0, details: "Generate search queries; refine them when more evidence is needed." },
  { stage_id: 3, stage_name: "Retrieve sources", status: "pending", duration_ms: 0, details: "Find reachable pages and retrieve their text." },
  { stage_id: 4, stage_name: "Extract records", status: "pending", duration_ms: 0, details: "Use the selected model to read source passages." },
  { stage_id: 5, stage_name: "Validate evidence", status: "pending", duration_ms: 0, details: "Check source support, confidence, and duplicate records." },
  { stage_id: 6, stage_name: "Save results", status: "pending", duration_ms: 0, details: "Persist records with their source citations." },
];
const STAGE_IDS: Record<string, number> = { planning: 1, discovering: 2, collecting: 3, extracting: 4, validating: 5, replanning: 2, finalizing: 6 };

function CreateCollectionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialPrompt = searchParams.get("prompt") || "";

  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [isRunning, setIsRunning] = useState(false);
  const [currentStageId, setCurrentStageId] = useState(1);
  const [stages, setStages] = useState<WorkflowStage[]>(INITIAL_STAGES);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [modelSelection, setModelSelection] = useState<ModelSelection>({ provider: "local", model: "qwen2.5-coder:1.5b-instruct", allow_external: false });
  const [modelReady, setModelReady] = useState(false);
  const canRun = modelReady && (modelSelection.provider === "local" || modelSelection.allow_external);

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

  const runCollection = async (data: CollectionFormValues) => {
    if (isRunning || !canRun) return;
    setErrorMessage(null);
    setStep(3);
    setIsRunning(true);
    setCurrentStageId(1);

    try {
      const response = await executeGroundedSearch(data.prompt, modelSelection, (stage) => setCurrentStageId(STAGE_IDS[stage] || 1));
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
              {modelSelection.provider === "local" ? "Local · Ollama" : "NVIDIA"} · {modelSelection.model}
              <br />Progress follows the server. Model calls and workflows have bounded time limits.
            </p>

            <DagExecutionFeed currentStageId={currentStageId} stages={stages} />
          </div>
        ) : step === 2 ? (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#657a98]">Review requirement</div>
            <h2 className="mt-2 text-[22px] font-bold tracking-[-0.025em] text-[#10213a]">Ready to collect?</h2>
            <p className="mt-1 text-[13px] text-[#68778c]">Confirm the request before the workflow starts searching external sources.</p>

            <div className="mt-6 rounded-[9px] border border-[#dce4ed] bg-[#f7f9fc] p-4">
              <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7b899c]">Collection requirement</div>
              <p className="mt-2 text-[14px] leading-6 text-[#23354f]">{promptValue}</p>
              <p className="mt-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--muted)]">Processing: {modelSelection.provider === "local" ? "Local · Ollama" : "NVIDIA"} · {modelSelection.model}</p>
              {modelSelection.provider === "nvidia" && <p className="mt-1 text-xs text-[var(--muted)]">You allowed NVIDIA to process this collection&apos;s prompt, fields, queries, and web passages.</p>}
            </div>

            <div className="mt-8 flex items-center justify-between border-t border-[#edf1f5] pt-5">
              <button
                type="button"
                onClick={() => setStep(1)}
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

            <form onSubmit={handleSubmit(() => { if (canRun) setStep(2); })} noValidate className="mt-6">
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
                <p role="alert" className="mt-3 rounded-[7px] border border-[#efd2d6] bg-[#fff7f8] px-3 py-2 text-xs text-[#a63c47]">{errorMessage}</p>
              )}

              <ModelSelector value={modelSelection} onChange={setModelSelection} onReadyChange={setModelReady} />

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
                  disabled={!canRun}
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
