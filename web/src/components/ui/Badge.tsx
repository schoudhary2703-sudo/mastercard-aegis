import type { ReactNode } from "react";
import type { RecommendedAction } from "../../types/aegis";

type Variant =
  | "neutral"
  | "attack"
  | "defend"
  | "risk-low"
  | "risk-medium"
  | "risk-high";

const VARIANT_CLASSES: Record<Variant, string> = {
  neutral: "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)] border-[var(--color-border)]",
  attack: "bg-[var(--color-attack-100)] text-[var(--color-attack-600)] border-transparent",
  defend: "bg-[var(--color-defend-100)] text-[var(--color-defend-600)] border-transparent",
  "risk-low": "bg-[var(--color-risk-low-100)] text-[var(--color-risk-low-600)] border-transparent",
  "risk-medium": "bg-[var(--color-risk-medium-100)] text-[var(--color-risk-medium-600)] border-transparent",
  "risk-high": "bg-[var(--color-risk-high-100)] text-[var(--color-risk-high-600)] border-transparent",
};

export function Badge({ variant = "neutral", children }: { variant?: Variant; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${VARIANT_CLASSES[variant]}`}
    >
      {children}
    </span>
  );
}

const ACTION_VARIANT: Record<RecommendedAction, Variant> = {
  approve: "risk-low",
  step_up: "risk-medium",
  review: "risk-medium",
  decline: "risk-high",
};

const ACTION_LABEL: Record<RecommendedAction, string> = {
  approve: "Approve",
  step_up: "Step-up",
  review: "Review",
  decline: "Decline",
};

export function ActionBadge({ action }: { action: RecommendedAction }) {
  return <Badge variant={ACTION_VARIANT[action]}>{ACTION_LABEL[action]}</Badge>;
}

export function RiskBadge({ score }: { score: number }) {
  const variant: Variant = score >= 0.65 ? "risk-high" : score >= 0.4 ? "risk-medium" : "risk-low";
  return <Badge variant={variant}>{(score * 100).toFixed(0)}% risk</Badge>;
}
