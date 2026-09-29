"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, X } from "lucide-react";

const EXAMPLES = [
  {
    label: "Find job openings",
    prompt: "Find currently open Rust backend developer roles in Bangalore from official company career pages with salary.",
  },
  {
    label: "Sales leads",
    prompt: "Find 100 AI startups in South India that raised funding in the last 18 months, including founder, website, location, and funding round.",
  },
  {
    label: "Sponsor opportunities",
    prompt: "Find companies that could sponsor a robotics hackathon in Tamil Nadu, with evidence of CSR, previous sponsorships, contact information, and relevance.",
  },
  {
    label: "Market data",
    prompt: "Track competitor pricing for top AI CRM software in 2026 with pricing tiers, enterprise features, and source citations.",
  },
  {
    label: "Suppliers",
    prompt: "Build a supplier shortlist for industrial robotics and automation distributors in Tamil Nadu with pricing, availability, and catalog evidence.",
  },
];

export function HeroSection() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    router.push(`/collections/new?prompt=${encodeURIComponent(prompt)}`);
  };

  const handleChipClick = (examplePrompt: string) => {
    router.push(`/collections/new?prompt=${encodeURIComponent(examplePrompt)}`);
  };

  return (
    <section className="relative overflow-clip rounded-[12px] border border-[#dbe4ee] bg-[#f5f8fc] px-5 py-8 sm:px-8 lg:min-h-[clamp(360px,24vw,480px)] lg:px-10 lg:py-10 2xl:flex 2xl:items-center 2xl:px-14 2xl:py-12">
      <div className="relative z-10 max-w-[760px] 2xl:max-w-[920px]">
        <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[#56739c] 2xl:text-[12px]">
          Data intelligence
        </div>
        <h1 className="mt-3 max-w-[640px] text-[34px] font-bold leading-[1.08] tracking-[-0.04em] text-[#10213a] sm:text-[42px] 2xl:max-w-[790px] 2xl:text-[54px]">
          Turn business questions<br className="hidden sm:block" /> into real data.
        </h1>
        <p className="mt-3 max-w-[620px] text-sm leading-6 text-[#53647c] sm:text-[15px] 2xl:max-w-[760px] 2xl:text-[17px] 2xl:leading-7">
          Find, verify, and structure information from across the web—with the source trail intact.
        </p>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="mt-6 flex max-w-[760px] flex-col gap-2 rounded-[10px] border border-[#bfcde0] bg-white p-1.5 shadow-[0_1px_2px_rgba(27,48,75,0.05)] transition-colors focus-within:border-[#6d9ee8] focus-within:ring-3 focus-within:ring-[#246bde]/10 sm:flex-row sm:items-center 2xl:mt-8 2xl:max-w-[920px] 2xl:p-2"
        >
          <label htmlFor="collection-prompt" className="sr-only">
            Describe the data you want to collect
          </label>
          <div className="relative min-w-0 flex-1">
            <input
              id="collection-prompt"
              type="text"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Describe what you want to collect..."
              className="h-10 w-full bg-transparent px-3 pr-10 text-[13px] text-[#172a44] outline-none placeholder:text-[#8b98aa] 2xl:h-11 2xl:px-4 2xl:text-[14px]"
            />
            {prompt && (
              <button
                type="button"
                onClick={() => setPrompt("")}
                aria-label="Clear collection prompt"
                className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-[#7a899e] hover:bg-[#edf2f7] hover:text-[#23354f]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <button
            type="submit"
            disabled={!prompt.trim()}
            className="flex h-10 shrink-0 items-center justify-center gap-2 rounded-[7px] bg-[#246bde] px-5 text-[13px] font-semibold text-white transition-colors hover:bg-[#1959c2] active:bg-[#154ca5] disabled:bg-[#a9bddc] 2xl:h-11 2xl:px-6 2xl:text-[14px]"
          >
            <span>Create collection</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] 2xl:mt-5 2xl:text-[12px]">
          <span className="font-medium text-[#77869a]">Try an example:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example.label}
              type="button"
              onClick={() => handleChipClick(example.prompt)}
              className="rounded-full border border-[#d7e0ea] bg-white/85 px-3 py-1.5 font-medium text-[#4f6078] transition-colors hover:border-[#aebdd0] hover:bg-white hover:text-[#10213a]"
            >
              {example.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[34%] overflow-hidden opacity-70 sm:h-[42%] lg:inset-y-0 lg:left-auto lg:h-full lg:w-[54%] lg:opacity-100"
        aria-hidden="true"
      >
        <div className="absolute right-9 top-9 hidden text-right text-[13px] italic text-[#667994] lg:block">
          “Information creates opportunity.”
          <div className="ml-auto mt-3 h-px w-6 bg-[#7891b1]" />
        </div>
        <svg
          className="absolute bottom-[-1px] right-0 h-full min-h-[180px] w-full"
          viewBox="0 0 900 420"
          preserveAspectRatio="xMaxYMax slice"
        >
          <path
            d="M0 420C58 380 108 279 177 267C236 276 278 228 335 238C394 249 429 199 486 207C548 216 589 164 647 174C706 184 748 139 802 146C840 151 870 136 900 120V420Z"
            fill="#E8EFF6"
          />
          <path
            d="M0 420C68 383 137 303 207 304C275 314 316 267 377 279C438 291 477 241 539 251C603 261 645 207 704 221C763 234 814 194 900 183V420Z"
            fill="#DAE5EF"
          />
          <path
            d="M113 420C170 389 222 332 268 339C311 346 334 301 374 276C412 252 442 324 485 331C533 339 575 267 617 239C659 211 697 302 740 309C784 316 824 262 900 235V420Z"
            fill="#C8D8E7"
          />
          <path
            d="M311 420C353 385 394 333 429 325C467 317 492 370 531 373C575 377 623 289 667 264C712 238 747 341 787 348C827 355 855 310 900 292V420Z"
            fill="#B8CDDF"
          />
          <path
            d="M0 327C91 308 135 280 202 289C269 298 315 251 376 263C438 275 480 224 541 235C608 247 646 191 706 205C769 219 812 177 900 163"
            fill="none"
            stroke="#9EB7CF"
            strokeWidth="1.4"
          />
          <path
            d="M620 242C636 230 650 218 667 207C681 221 690 235 700 249M416 292C421 285 425 280 429 277C438 285 444 295 451 307"
            fill="none"
            stroke="#F5F8FB"
            strokeLinecap="round"
            strokeWidth="3"
            opacity="0.78"
          />
        </svg>
      </div>
    </section>
  );
}
