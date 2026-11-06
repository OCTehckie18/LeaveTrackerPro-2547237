import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, FileCheck2, ListChecks, ScrollText, ShieldCheck, Smartphone } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Avatar, FieldError, StatusBadge } from "../components/ui";
import { ApiError, api } from "../lib/api";

const schema = z.object({
  email: z.string().trim().min(1, "Please enter your email address.").email("Please enter a valid email address."),
  password: z.string().min(1, "Please enter your password."),
});
type Values = z.infer<typeof schema>;

const DEMO = import.meta.env.VITE_DEMO_MODE === "true";
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD ?? "";
const DEMO_ACCOUNTS = [
  ["john@acme.test", "John Mathew", "Employee"],
  ["jane@acme.test", "Jane Dsouza", "Employee"],
  ["manager@acme.test", "Meera Nair", "Manager"],
  ["hod@acme.test", "Harish Rao", "Head of Department"],
  ["priya@acme.test", "Priya Sharma", "Manager (other team)"],
  ["raj@acme.test", "Raj Kapoor", "Employee (other team)"],
] as const;

const FEATURES = [
  [ListChecks, "Clear approvals", "Manager first, then HOD for leave over 3 days."],
  [FileCheck2, "Documents attached", "Certificates travel with the request."],
  [ScrollText, "Full audit trail", "Every action recorded and tamper-resistant."],
  [Smartphone, "Works everywhere", "Phone, tablet or laptop."],
] as const;

export default function Login() {
  const nav = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(schema), mode: "onTouched" });

  const login = useMutation({
    mutationFn: (v: Values) => api.post("/auth/login", v),
    onSuccess: async () => {
      await qc.resetQueries({ queryKey: ["me"] });
      const from = (location.state as { from?: string } | null)?.from;
      nav(from && from !== "/login" ? from : "/", { replace: true });
    },
    onError: (e) => setFormError(e instanceof ApiError ? e.message : "Something went wrong. Please try again."),
  });

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden bg-linear-to-br from-[#0747a6] via-[#1d4ed8] to-[#5e4db2] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-white/10 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -left-16 size-96 rounded-full bg-[#8777d9]/30 blur-3xl" />
        <div className="relative flex items-center gap-2.5 text-lg font-semibold">
          <span className="grid size-9 place-items-center rounded-md bg-white/15 ring-1 ring-white/30">
            <ShieldCheck className="size-5" aria-hidden="true" />
          </span>
          LeaveTrackerPro
        </div>

        <div className="relative max-w-md">
          <h1 className="text-4xl leading-tight font-semibold tracking-tight">Time off, without the back-and-forth.</h1>
          <p className="mt-3 text-white/80">Request leave, follow every approval step, and keep a clean record, all in one place.</p>
          <ul className="mt-8 space-y-4">
            {FEATURES.map(([Icon, title, text]) => (
              <li key={title} className="flex gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-md bg-white/12 ring-1 ring-white/20">
                  <Icon className="size-[18px]" aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-medium">{title}</span>
                  <span className="text-sm text-white/75">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* Decorative product preview */}
        <div className="relative max-w-sm rounded-lg bg-white p-4 text-[#172b4d] shadow-2xl ring-1 ring-black/10" aria-hidden="true">
          <div className="flex items-center gap-2.5">
            <Avatar name="John Mathew" size="sm" />
            <div className="flex-1">
              <p className="text-sm font-semibold">12 Dec – 16 Dec 2026</p>
              <p className="text-xs text-[#5e6c84]">LT-24 · 5 days sick leave</p>
            </div>
            <StatusBadge status="PENDING_HOD" />
          </div>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] font-medium text-[#5e6c84]">
            <span className="rounded-full bg-[#dcfff1] px-2 py-0.5 text-[#216e4e]">Manager ✓</span>
            <span>→</span>
            <span className="rounded-full bg-[#f3f0ff] px-2 py-0.5 text-[#5e4db2]">HOD</span>
          </div>
        </div>
      </aside>

      {/* Form */}
      <main className="flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 text-lg font-semibold lg:hidden">
            <span className="grid size-9 place-items-center rounded-md bg-linear-to-br from-[#1d7afc] to-[#5e4db2] text-white">
              <ShieldCheck className="size-5" aria-hidden="true" />
            </span>
            LeaveTrackerPro
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your work email to continue.</p>

          <form
            className="mt-6 space-y-4"
            noValidate
            onSubmit={handleSubmit((v) => {
              setFormError(null);
              login.mutate(v);
            })}
          >
            {formError && (
              <p role="alert" className="rounded-md border border-danger-fg/30 bg-danger-bg px-3 py-2 text-sm text-danger-fg">
                {formError}
              </p>
            )}
            <div>
              <label htmlFor="email" className="label">Email</label>
              <input id="email" type="email" autoComplete="username" inputMode="email" className="input" {...register("email")} />
              <FieldError message={errors.email?.message} />
            </div>
            <div>
              <label htmlFor="password" className="label">Password</label>
              <div className="relative">
                <input id="password" type={show ? "text" : "password"} autoComplete="current-password" className="input pr-11" {...register("password")} />
                <button
                  type="button"
                  onClick={() => setShow((s) => !s)}
                  className="absolute top-0 right-0 grid size-11 place-items-center text-muted md:size-9"
                  aria-label={show ? "Hide password" : "Show password"}
                >
                  {show ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
                </button>
              </div>
              <FieldError message={errors.password?.message} />
            </div>
            <button type="submit" className="btn-primary w-full md:min-h-10" disabled={login.isPending}>
              {login.isPending ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {DEMO && (
            <section className="mt-8" aria-labelledby="demo-title">
              <div className="flex items-center gap-3">
                <span className="h-px flex-1 bg-border" />
                <h3 id="demo-title" className="text-[11px] font-bold tracking-wider text-muted uppercase">Try a demo account</h3>
                <span className="h-px flex-1 bg-border" />
              </div>
              <ul className="mt-4 grid gap-2 sm:grid-cols-2">
                {DEMO_ACCOUNTS.map(([email, name, role]) => (
                  <li key={email}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2.5 rounded-md border border-border bg-surface p-2 text-left hover:border-primary hover:bg-hover"
                      onClick={() => {
                        setValue("email", email, { shouldValidate: true });
                        setValue("password", DEMO_PASSWORD, { shouldValidate: true });
                      }}
                    >
                      <Avatar name={name} size="sm" />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{name}</span>
                        <span className="block truncate text-xs text-muted">{role}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-center text-xs text-muted">
                Pick one to fill the form. Shared demo: don't enter real personal or medical information.
              </p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
