import { Suspense } from "react";
import { AuthForm } from "@/components/auth/AuthForm";
export const metadata = { title: "Sign in" };
export default function LoginPage() {
  return <Suspense fallback={<main className="min-h-dvh bg-[var(--background)] p-8"><p role="status">Loading sign in…</p></main>}><AuthForm mode="login" /></Suspense>;
}
