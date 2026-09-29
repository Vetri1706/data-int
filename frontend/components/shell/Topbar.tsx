"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Menu, Search, X } from "lucide-react";
import { AccountMenu } from "@/components/auth/AccountMenu";

interface TopbarProps {
  onMenuOpen: () => void;
}

export function Topbar({ onMenuOpen }: TopbarProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const committed = query.trim();
    if (!committed) return;
    router.push(`/collections?query=${encodeURIComponent(committed)}`);
  };

  return (
    <header className="sticky top-0 z-30 flex h-[clamp(56px,3.4vw,68px)] w-full items-center justify-between border-b border-[#e4eaf1] bg-white/95 px-[var(--workspace-inline)] backdrop-blur-md">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <button
          type="button"
          onClick={onMenuOpen}
          aria-label="Open navigation"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[#dbe3ec] bg-white text-[#52627a] hover:bg-[#f4f7fa] lg:hidden"
        >
          <Menu className="h-4 w-4" />
        </button>

        <form
          onSubmit={handleSubmit}
          noValidate
          role="search"
          className="relative flex w-full max-w-[clamp(520px,34vw,720px)] items-center"
        >
          <Search className="pointer-events-none absolute left-3 h-4 w-4 text-[#718096]" />
          <input
            type="text"
            inputMode="search"
            aria-label="Search collections and datasets"
            placeholder="Search collections, datasets, sources…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-9 w-full rounded-[8px] border border-[#e0e7ef] bg-[#f5f7fa] pl-9 pr-9 text-xs text-[#23354f] outline-none transition-colors placeholder:text-[#8794a7] focus:border-[#8eb3ec] focus:bg-white focus:ring-2 focus:ring-[#246bde]/10 2xl:h-10 2xl:text-[13px]"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              aria-label="Clear global search"
              className="absolute right-1.5 flex h-7 w-7 items-center justify-center rounded-md text-[#7b899c] hover:bg-[#e9eef4] hover:text-[#23354f]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </form>
      </div>

      <AccountMenu />
    </header>
  );
}
