"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, signedOut, error, refresh } = useAuth();
  const publicRoute = pathname === "/login" || pathname === "/register";
  useEffect(() => {
    if (!publicRoute && !loading && !user && !error) {
      router.replace(signedOut ? "/login?signedOut=1" : `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    }
  }, [publicRoute, loading, signedOut, user, error, pathname, router]);
  if (publicRoute) return <>{children}</>;
  if (loading || !user || error) return (
    <main className="flex min-h-dvh items-center justify-center bg-[var(--background)] px-6">
      {error ? <div className="max-w-sm text-center"><p role="alert" className="text-sm text-[var(--muted)]">{error}</p><button type="button" onClick={() => void refresh()} className="mt-4 min-h-11 rounded-lg bg-[var(--primary)] px-5 text-sm font-semibold text-white hover:bg-[var(--primary-hover)]">Try again</button></div>
        : <p role="status" className="flex items-center gap-3 text-sm text-[var(--muted)]"><Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />Checking your session…</p>}
    </main>
  );
  return <WorkspaceShell key={user.id}>{children}</WorkspaceShell>;
}

function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const [navigationOpen, setNavigationOpen] = useState(false);

  return (
    <div className="app-canvas min-h-dvh bg-[#e9eef4] text-[#10213a]">
      <div className="app-frame mx-auto flex w-full rounded-none border-0 border-[#d7e0ea] bg-[#f7f9fc] shadow-none lg:rounded-[14px] lg:border lg:shadow-[0_18px_55px_rgba(34,52,73,0.10)]">
        <Sidebar
          open={navigationOpen}
          onClose={() => setNavigationOpen(false)}
        />

        {navigationOpen && (
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setNavigationOpen(false)}
            className="fixed inset-0 z-40 bg-[#10213a]/25 backdrop-blur-[2px] lg:hidden"
          />
        )}

        <div className="min-w-0 flex-1">
          <Topbar onMenuOpen={() => setNavigationOpen(true)} />
          <main className="app-main">{children}</main>
        </div>
      </div>
    </div>
  );
}
