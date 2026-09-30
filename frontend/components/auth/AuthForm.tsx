"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { ArrowRight, Check, Eye, EyeOff, Link2, Loader2 } from "lucide-react";
import { useAuth } from "./AuthProvider";
import { ApiError } from "@/lib/api";
import { safeReturnPath } from "@/lib/auth-navigation";
import { BrandMark } from "@/components/BrandMark";

type Values = { name: string; email: string; password: string; confirm: string };

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const isRegister = mode === "register";
  const { user, loading, signIn, signUp } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeReturnPath(params.get("next"));
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const mounted = useRef(true);
  const busy = useRef(false);
  const { register, handleSubmit, getValues, resetField, setError: setFieldError, formState: { errors, isSubmitting } } = useForm<Values>({
    defaultValues: { name: "", email: "", password: "", confirm: "" }, mode: "onSubmit", reValidateMode: "onChange",
  });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (user) router.replace(next); }, [user, router, next]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function submit(values: Values) {
    if (busy.current) return;
    busy.current = true;
    setError(null);
    try {
      if (isRegister) await signUp(values.email.trim(), values.password, values.name.trim());
      else await signIn(values.email.trim(), values.password);
      if (mounted.current) router.replace(next);
    } catch (cause) {
      if (!mounted.current) return;
      resetField("password"); resetField("confirm"); setShowPassword(false);
      if (isRegister && cause instanceof ApiError && cause.message.includes("already registered")) {
        setFieldError("email", { message: "An account with this email already exists. Sign in instead." }, { shouldFocus: true });
      } else {
        setError(cause instanceof ApiError && cause.status === 401 ? "Email or password is incorrect. Please try again."
          : "We couldn’t complete that request. Please try again. If you just created an account, try signing in.");
      }
    } finally { busy.current = false; }
  }

  const fieldClass = "h-12 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] px-3.5 text-[15px] text-[var(--foreground)] outline-none transition-colors placeholder:text-[var(--muted)]/60 focus:border-[var(--primary)] focus:ring-3 focus:ring-[var(--primary-soft)] aria-invalid:border-[var(--danger)] disabled:bg-[var(--surface-subtle)]";
  const labelClass = "mb-2 block text-[13px] font-semibold text-[var(--foreground)]";
  const fieldError = (name: keyof Values) => errors[name] && <p id={`${name}-error`} className="mt-1.5 text-xs leading-relaxed text-[var(--danger)]">{errors[name]?.message}</p>;
  const authLink = (route: string) => `${route}${next === "/" ? "" : `?next=${encodeURIComponent(next)}`}`;

  return (
    <main className="auth-page flex min-h-dvh flex-col bg-[var(--background)] px-5 py-7 sm:px-8 sm:py-9">
      <header className="mx-auto flex w-full max-w-[1200px] items-center justify-between gap-4">
        <Link href="/login" aria-label="Datavault home" className="flex items-center gap-2.5 rounded-md text-[17px] font-bold tracking-tight">
          <BrandMark />Datavault
        </Link>
        <Link href={authLink(isRegister ? "/login" : "/register")} className="flex min-h-11 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3.5 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-[var(--primary-soft)] sm:px-4 sm:text-[13px]">
          {isRegister ? "Sign in" : "Create account"}<ArrowRight aria-hidden="true" className="size-3.5" />
        </Link>
      </header>

      <div className="mx-auto grid w-full max-w-[1056px] flex-1 items-center gap-16 py-12 md:grid-cols-[1fr_1fr] lg:gap-28 lg:py-16">
        <section className="hidden md:block" aria-label="About Datavault">
          <p className="mb-5 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">Your research workspace</p>
          <h2 className="max-w-[430px] text-[clamp(32px,3.4vw,48px)] leading-[1.14] font-semibold tracking-[-0.045em]">Better questions.<br />More useful data.</h2>
          <p className="mt-6 max-w-[370px] text-[15px] leading-7 text-[var(--muted)]">Turn a business question into a collection you can inspect, verify, and use.</p>
          <div className="mt-12 border-t border-[var(--border)] pt-7">
            <div className="flex items-start gap-3.5"><Link2 className="mt-0.5 size-[18px] shrink-0 text-[var(--primary)]" aria-hidden="true" /><div><p className="text-sm font-semibold">Keep the source in sight</p><p className="mt-1.5 max-w-[330px] text-[13px] leading-6 text-[var(--muted)]">Trace results back to their evidence, with citations alongside the data.</p></div></div>
            <div className="mt-6 flex items-center gap-3.5 text-xs text-[var(--muted)]"><Check aria-hidden="true" className="size-[18px] text-[var(--muted)]" />One place for collections, datasets, and sources.</div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-[420px]" aria-labelledby="auth-heading">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">{isRegister ? "Get started" : "Welcome back"}</p>
          <h1 id="auth-heading" className="text-[30px] font-semibold leading-tight tracking-[-0.035em]">{isRegister ? "Create your account" : "Sign in to Datavault"}</h1>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{isRegister ? "Set up your workspace and start your first collection." : "Your collections and sources, right where you left them."}</p>
          {params.get("signedOut") === "1" && <p role="status" className="mt-5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--success)]">You’ve been signed out.</p>}
          <form noValidate onSubmit={(event) => { void handleSubmit(submit)(event); }} aria-busy={isSubmitting} className="mt-8 space-y-5">
            {error && <p ref={errorRef} role="alert" tabIndex={-1} className="rounded-lg border border-[var(--danger)]/30 bg-[var(--surface)] px-4 py-3 text-sm leading-6 text-[var(--danger)]">{error}</p>}
            {isRegister && <div><label htmlFor="name" className={labelClass}>Full name</label><input id="name" type="text" autoComplete="name" required maxLength={100} disabled={isSubmitting} placeholder="Your name" className={fieldClass} aria-invalid={!!errors.name} aria-describedby={errors.name ? "name-error" : undefined} {...register("name", { validate: (value) => !!value.trim() || "Enter your name.", maxLength: { value: 100, message: "Use 100 characters or fewer." } })} />{fieldError("name")}</div>}
            <div><label htmlFor="email" className={labelClass}>Email address</label><input id="email" type="email" inputMode="email" autoComplete="email" required maxLength={254} disabled={isSubmitting} placeholder="you@company.com" className={fieldClass} aria-invalid={!!errors.email} aria-describedby={errors.email ? "email-error" : undefined} {...register("email", { required: "Enter your email address.", validate: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()) || "Enter a valid email address." })} />{fieldError("email")}</div>
            <div>
              <label htmlFor="password" className={labelClass}>Password</label>
              <div className="relative"><input id="password" type={showPassword ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} required disabled={isSubmitting} className={`${fieldClass} pr-12`} aria-invalid={!!errors.password} aria-describedby={[isRegister ? "password-hint" : "", errors.password ? "password-error" : ""].filter(Boolean).join(" ") || undefined} {...register("password", { required: "Enter your password.", minLength: isRegister ? { value: 8, message: "Use at least 8 characters." } : undefined, maxLength: { value: 256, message: "Use 256 characters or fewer." } })} /><button type="button" disabled={isSubmitting} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)} className="absolute inset-y-1 right-1 flex w-10 items-center justify-center rounded-md text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--foreground)]">{showPassword ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}</button></div>
              {isRegister && <p id="password-hint" className="mt-2 text-xs text-[var(--muted)]">Use at least 8 characters.</p>}{fieldError("password")}
            </div>
            {isRegister && <div><label htmlFor="confirm" className={labelClass}>Confirm password</label><input id="confirm" type={showPassword ? "text" : "password"} autoComplete="new-password" required disabled={isSubmitting} className={fieldClass} aria-invalid={!!errors.confirm} aria-describedby={errors.confirm ? "confirm-error" : undefined} {...register("confirm", { required: "Confirm your password.", validate: (value) => value === getValues("password") || "Passwords don’t match." })} />{fieldError("confirm")}</div>}
            <button type="submit" disabled={isSubmitting || loading || !!user} className="flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[var(--primary)] text-sm font-semibold text-white transition-colors hover:bg-[var(--primary-hover)] active:translate-y-px disabled:opacity-60">
              {isSubmitting ? <><Loader2 aria-hidden="true" className="size-4 animate-spin" />{isRegister ? "Creating account…" : "Signing in…"}</> : <>{isRegister ? "Create account" : "Sign in"}<ArrowRight aria-hidden="true" className="size-4" /></>}
            </button>
            {isSubmitting && <span role="status" className="sr-only">{isRegister ? "Creating your account" : "Signing in"}</span>}
          </form>
          <p className="mt-7 text-center text-[13px] text-[var(--muted)]">{isRegister ? "Already have an account?" : "New to Datavault?"}{" "}<Link href={authLink(isRegister ? "/login" : "/register")} className="rounded-sm font-semibold text-[var(--primary)] underline-offset-4 hover:underline">{isRegister ? "Sign in" : "Create an account"}</Link></p>
        </section>
      </div>
      <footer className="mx-auto w-full max-w-[1200px] border-t border-[var(--border)] pt-5 text-xs text-[var(--muted)]">Datavault <span aria-hidden="true" className="px-2">/</span> From questions to evidence.</footer>
    </main>
  );
}
