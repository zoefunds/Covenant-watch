import React from "react";
import Link from "next/link";

export function Button({
  children,
  variant = "primary",
  className = "",
  href,
  disabled,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; href?: string }) {
  const base =
    "focus-ring inline-flex items-center justify-center gap-2 rounded font-medium text-sm px-4 py-2.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants: Record<string, string> = {
    primary: "bg-primary-container text-on-primary-container hover:brightness-110",
    secondary: "bg-surface-container-high text-on-surface border border-outline-variant hover:bg-surface-container-highest",
    ghost: "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high",
    danger: "bg-error-container text-on-error-container hover:brightness-110",
  };
  const cls = `${base} ${variants[variant]} ${className}`;
  if (href) {
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  }
  return (
    <button className={cls} disabled={disabled} {...rest}>
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-outline-variant bg-surface-container-low p-5 ${className}`}>
      {children}
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-on-surface">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-on-surface-variant">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-error">{error}</span>}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`focus-ring w-full rounded border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm text-on-surface placeholder:text-outline focus:border-primary-container ${props.className || ""}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`focus-ring w-full rounded border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm text-on-surface focus:border-primary-container ${props.className || ""}`}
    />
  );
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`focus-ring w-full rounded border border-outline-variant bg-surface-container-lowest px-3 py-2 text-sm text-on-surface placeholder:text-outline focus:border-primary-container ${props.className || ""}`}
    />
  );
}

export function Mono({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`font-onchain ${className}`}>{children}</span>;
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-outline-variant py-16 text-center">
      <p className="text-sm font-medium text-on-surface">{title}</p>
      {body && <p className="max-w-sm text-sm text-on-surface-variant">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", body }: { title?: string; body?: string }) {
  return (
    <div className="rounded-lg border border-error/40 bg-error-container/10 p-5">
      <p className="text-sm font-medium text-error">{title}</p>
      {body && <p className="mt-1 text-sm text-on-surface-variant">{body}</p>}
    </div>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-on-surface-variant">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-primary-container border-t-transparent" />
      {label}
    </div>
  );
}
