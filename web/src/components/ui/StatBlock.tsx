import type { ReactNode } from "react";
import { CountUp } from "./CountUp";

/**
 * The artifact a number came from, shown next to the number itself rather
 * than once per section. Traceability is the point of this project, so it is
 * rendered as a consistent, recognisable mark.
 */
export function SourceLink({ source, className = "" }: { source?: string; className?: string }) {
  if (!source) return null;
  const file = source.split("/").pop() ?? source;
  return (
    <span
      title={source}
      className={`t-mono-sm inline-flex max-w-full items-center gap-1 truncate text-[var(--color-ink-faint)] ${className}`}
    >
      <span aria-hidden="true" className="text-[var(--color-defend-600)]">
        ◇
      </span>
      <span className="truncate">{file}</span>
    </span>
  );
}

type Tone = "neutral" | "good" | "bad" | "accent";

const TONE: Record<Tone, string> = {
  neutral: "text-[var(--color-ink)]",
  good: "text-[var(--color-risk-low-600)]",
  bad: "text-[var(--color-risk-high-600)]",
  accent: "text-[var(--color-accent-500)]",
};

/**
 * One measured result: the number, what it is, where it came from, and what
 * it means. Replaces the tile grids -- a judge should be able to read any
 * single one of these standalone and know whether to trust it.
 */
export function StatBlock({
  label,
  value,
  format,
  display,
  meaning,
  source,
  tone = "neutral",
  size = "default",
}: {
  label: string;
  /** Numeric value, counted up. Omit and pass `display` for non-numeric values. */
  value?: number | null;
  format?: (n: number) => string;
  display?: ReactNode;
  meaning?: string;
  source?: string;
  tone?: Tone;
  size?: "default" | "xl";
}) {
  const numberClass = `${size === "xl" ? "t-stat-xl" : "t-stat"} ${TONE[tone]}`;

  return (
    <div className="flex flex-col gap-1.5">
      <p className="t-eyebrow text-[var(--color-ink-faint)]">{label}</p>
      <p className={numberClass}>
        {display ?? (
          <CountUp value={value} format={format ?? ((n) => n.toFixed(1))} />
        )}
      </p>
      {meaning && <p className="t-body-sm text-[var(--color-ink-muted)]">{meaning}</p>}
      <SourceLink source={source} />
    </div>
  );
}

/** Signed change chip, coloured by outcome rather than direction. */
export function MetricDelta({ value, suffix = "" }: { value: number; suffix?: string }) {
  const good = value >= 0;
  return (
    <span
      className={`t-mono-sm inline-flex items-center gap-0.5 ${
        good ? "text-[var(--color-risk-low-600)]" : "text-[var(--color-risk-high-600)]"
      }`}
    >
      {good ? "▲" : "▼"} {good ? "+" : ""}
      {value.toFixed(1)}
      {suffix}
    </span>
  );
}
