import { Suspense } from "react";
import { AuthForm } from "@/components/auth/AuthForm";
export const metadata = { title: "Create account" };
export default function RegisterPage() {
  return <Suspense fallback={<main className="min-h-dvh bg-[var(--background)] p-8"><p role="status">Loading registration…</p></main>}><AuthForm mode="register" /></Suspense>;
}
