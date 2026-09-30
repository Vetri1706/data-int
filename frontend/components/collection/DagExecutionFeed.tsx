"use client";

import React from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { WorkflowStage } from "@/lib/types";

interface DagExecutionFeedProps {
  currentStageId: number;
  stages: WorkflowStage[];
}

export function DagExecutionFeed({ currentStageId, stages }: DagExecutionFeedProps) {
  return (
    <ol className="mx-auto mt-6 max-w-[760px] divide-y divide-[#e1e7ee] border-y border-[#dce4ed] text-left">
      {stages.map((stage) => {
        const isDone = stage.status === "completed";
        const isCurrent = stage.stage_id === currentStageId;

        return (
          <li
            key={stage.stage_id}
            className={`flex items-start gap-3 px-1 py-3 text-[11px] transition-colors ${
              isCurrent
                ? "bg-[#f0f5fd]"
                : isDone
                ? "bg-white"
                : "opacity-45"
            }`}
          >
            <div className="mt-0.5 shrink-0">
              {isDone ? (
                <CheckCircle2 className="h-4 w-4 text-[#238a59]" />
              ) : isCurrent ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#246bde]" />
              ) : (
                <div className="h-4 w-4 rounded-full border border-[#bcc8d5]" />
              )}
            </div>

            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-[#23354f]">
                  {String(stage.stage_id).padStart(2, "0")} · {stage.stage_name}
                </span>
                {isDone && stage.duration_ms !== null && stage.duration_ms > 0 && (
                  <span className="font-mono text-[10px] text-[#7c899c]">
                    {stage.duration_ms}ms
                  </span>
                )}
              </div>
              <p className="mt-0.5 leading-4 text-[#66758a]">{stage.details}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
