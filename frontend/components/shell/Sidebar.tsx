"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  LayoutGrid,
  Database,
  Globe2,
  GitFork,
  History,
  Settings,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/components/auth/AuthProvider";

const NAV_ITEMS = [
  { label: "Overview", href: "/", icon: Home },
  { label: "Collections", href: "/collections", icon: LayoutGrid },
  { label: "Datasets", href: "/datasets", icon: Database },
  { label: "Sources", href: "/sources", icon: Globe2 },
  { label: "Workflows", href: "/workflows", icon: GitFork },
  { label: "History", href: "/history", icon: History },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();
  const name = user?.name?.trim() || user?.email || "Your account";
  const settingsActive = pathname === "/settings";

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex w-[var(--workspace-sidebar)] flex-col justify-between border-r border-[#e1e7ef] bg-white px-3 py-4 transition-transform duration-200 lg:relative lg:inset-auto lg:z-10 lg:min-h-full lg:translate-x-0 lg:rounded-l-[14px] 2xl:px-4 2xl:py-5",
        open ? "translate-x-0" : "-translate-x-full"
      )}
      aria-label="Primary navigation"
    >
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between px-1">
          <Link
            href="/"
            onClick={onClose}
            className="flex items-center gap-2.5 rounded-md px-1 py-1 select-none"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-[#246bde] text-white">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-hidden="true"
              >
                <path d="M6.5 16.5V7.5L13.75 12L6.5 16.5Z" fill="white" />
                <circle cx="16.4" cy="12" r="2.25" fill="#BFD5FF" />
              </svg>
            </div>
            <span className="text-[15px] font-bold tracking-[-0.025em] text-[#10213a]">
              Datavault
            </span>
          </Link>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex flex-col gap-1 2xl:gap-1.5" aria-label="Workspace">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.href === "/"
              ? pathname === "/"
              : item.href === "/collections"
              ? pathname === item.href || pathname.startsWith("/collections/")
              : pathname === item.href || pathname.startsWith(`${item.href}/`);

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "group flex min-h-10 items-center gap-3 rounded-[7px] px-3 py-2 text-[13px] font-medium transition-colors 2xl:min-h-11 2xl:text-[14px]",
                  isActive
                    ? "bg-[#eaf2ff] font-semibold text-[#174f9f]"
                    : "text-[#55657d] hover:bg-[#f4f7fa] hover:text-[#10213a]"
                )}
              >
                <Icon
                  className={cn(
                    "h-[15px] w-[15px] shrink-0 stroke-[1.8] transition-colors",
                    isActive ? "text-[#246bde]" : "text-[#738198] group-hover:text-[#40516b]"
                  )}
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="flex flex-col gap-2 border-t border-[#edf1f5] pt-3">
        <Link
          href="/settings"
          onClick={onClose}
          aria-current={settingsActive ? "page" : undefined}
          className={cn(
            "flex min-h-10 items-center gap-3 rounded-[7px] px-3 py-2 text-[13px] font-medium transition-colors 2xl:min-h-11 2xl:text-[14px]",
            settingsActive
              ? "bg-[#eaf2ff] font-semibold text-[#174f9f]"
              : "text-[#55657d] hover:bg-[#f4f7fa] hover:text-[#10213a]"
          )}
        >
          <Settings className={cn("h-[15px] w-[15px]", settingsActive ? "text-[#246bde]" : "text-[#738198]")} />
          <span>Settings</span>
        </Link>

        <div className="flex items-center gap-3 rounded-[7px] px-2 py-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#17345f] text-[11px] font-bold text-white">
            {name[0]?.toUpperCase()}
          </div>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-xs font-semibold text-[#10213a]">{name}</span>
            <span className="mt-0.5 truncate text-[10px] text-[#7b899c]">{user?.email}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
