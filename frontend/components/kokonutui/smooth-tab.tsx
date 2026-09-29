"use client";

/**
 * Adapted from Kokonut UI Smooth Tab for Datavault's product navigation.
 * @author @dorianbaffier / @kokonut-labs
 * @license MIT
 * @see https://kokonutui.com/docs/navigation/smooth-tab
 */

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export interface SmoothTabItem {
  id: string;
  title: string;
  count?: number;
}

interface SmoothTabProps {
  items: SmoothTabItem[];
  value: string;
  onValueChange: (value: string) => void;
  ariaLabel: string;
  className?: string;
}

export default function SmoothTab({
  items,
  value,
  onValueChange,
  ariaLabel,
  className,
}: SmoothTabProps) {
  const indicatorId = React.useId();
  const reduceMotion = useReducedMotion();
  const buttonRefs = React.useRef(new Map<string, HTMLButtonElement>());

  const moveSelection = (currentId: string, direction: 1 | -1) => {
    const currentIndex = items.findIndex((item) => item.id === currentId);
    const nextIndex = (currentIndex + direction + items.length) % items.length;
    const nextItem = items[nextIndex];
    onValueChange(nextItem.id);
    buttonRefs.current.get(nextItem.id)?.focus();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, itemId: string) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      moveSelection(itemId, 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      moveSelection(itemId, -1);
    } else if (event.key === "Home") {
      event.preventDefault();
      onValueChange(items[0].id);
      buttonRefs.current.get(items[0].id)?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      const last = items[items.length - 1];
      onValueChange(last.id);
      buttonRefs.current.get(last.id)?.focus();
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "flex min-w-max items-center gap-5 border-b border-[#dce4ed] text-[11px] font-semibold 2xl:gap-7 2xl:text-[13px]",
        className
      )}
    >
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(node) => {
              if (node) buttonRefs.current.set(item.id, node);
              else buttonRefs.current.delete(item.id);
            }}
            id={`tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={`panel-${item.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(item.id)}
            onKeyDown={(event) => handleKeyDown(event, item.id)}
            className={cn(
              "relative shrink-0 px-0.5 pb-2.5 pt-1 text-[#66758a] transition-colors hover:text-[#10213a]",
              selected && "text-[#174e9f]"
            )}
          >
            {item.title}{item.count === undefined ? "" : ` (${item.count})`}
            {selected && (
              <motion.span
                layoutId={`kokonut-tab-${indicatorId}`}
                aria-hidden="true"
                className="absolute inset-x-0 bottom-[-1px] h-0.5 rounded-full bg-[#246bde]"
                transition={
                  reduceMotion
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 420, damping: 34, mass: 0.55 }
                }
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
