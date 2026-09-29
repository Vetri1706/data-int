"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Loader2, LogOut, Settings } from "lucide-react";
import { useAuth } from "./AuthProvider";

export function AccountMenu() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const pending = useRef(false);
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node) && !pending.current) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  if (!user) return null;
  const name = user.name?.trim() || user.email;
  const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();

  async function logout() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(null);
    try { await signOut(); router.replace("/login?signedOut=1"); }
    catch { setError("Couldn’t sign out. Check your connection and try again."); }
    finally { pending.current = false; setBusy(false); }
  }

  return (
    <div ref={root} className="relative ml-3 shrink-0" onKeyDown={(event) => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
      if (open && ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') || []);
        const current = items.indexOf(document.activeElement as HTMLElement);
        const index = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items[index]?.focus();
      }
    }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget) && !pending.current) setOpen(false); }}>
      <button ref={trigger} type="button" aria-label={`Account menu for ${name}`} aria-haspopup="menu" aria-expanded={open} aria-controls="account-menu" onClick={() => setOpen(!open)} onKeyDown={(event) => { if (!open && event.key === "ArrowDown") { event.preventDefault(); setOpen(true); } }} className="flex min-h-11 items-center gap-2 rounded-lg px-1.5 text-[var(--foreground)] hover:bg-[var(--surface-subtle)] sm:px-2.5">
        <span className="flex size-8 items-center justify-center rounded-full bg-[var(--primary-soft)] text-[11px] font-bold text-[var(--primary)]">{initials}</span>
        <span className="hidden max-w-32 truncate text-xs font-semibold sm:block">{name}</span><ChevronDown aria-hidden="true" className="size-3.5 text-[var(--muted)]" />
      </button>
      {open && <div ref={menu} id="account-menu" role="menu" aria-label="Account" className="absolute top-full right-0 z-50 mt-2 w-64 max-w-[calc(100vw-40px)] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-1.5 shadow-lg">
        <div role="none" className="border-b border-[var(--border)] px-3 py-3"><p className="truncate text-sm font-semibold">{name}</p><p className="mt-1 truncate text-xs text-[var(--muted)]">{user.email}</p></div>
        <Link role="menuitem" href="/settings" onClick={() => setOpen(false)} className="mt-1 flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-[var(--foreground)] hover:bg-[var(--surface-subtle)]"><Settings className="size-4" aria-hidden="true" />Account settings</Link>
        <button role="menuitem" type="button" disabled={busy} onClick={() => void logout()} className="flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-left text-sm text-[var(--foreground)] hover:bg-[var(--primary-soft)] disabled:opacity-60">{busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <LogOut className="size-4" aria-hidden="true" />}{busy ? "Signing out…" : "Log out"}</button>
        {error && <p role="alert" className="px-3 py-2 text-xs leading-5 text-[var(--danger)]">{error}</p>}
      </div>}
    </div>
  );
}
