import { useState } from "react";
import { Link } from "react-router-dom";
import type {
  GenerationScaleDTO,
  GenerationScaleFamilyDTO,
  LandscapeResponseDTO,
  TaxonomyDTO,
  TaxonomyScenarioDTO,
} from "../../api/types";

/**
 * The fraud landscape: breadth (what AEGIS identified) and scale (what it
 * generated), both read straight from the API.
 *
 * The load-bearing honesty rule: 14 attacks are *identified*, 3 are *deeply
 * simulated*. Every card carries its own status badge and only a
 * DEEP SIMULATED entry links into Attack Lab, so the breadth catalog can
 * never read as "AEGIS simulates 14 attacks".
 *
 * No number here is written in the component. If the artifact does not carry
 * a value the cell renders a dash.
 */

const FAMILY_LABEL: Record<string, string> = {
  synthetic_identity_bustout: "Synthetic identity bust-out",
  mule_network_structuring: "Mule network structuring",
  adaptive_detector_evasion: "Adaptive detector evasion",
};

function titleCase(slug: string): string {
  return slug.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function compact(value: number | null | undefined): string {
  if (typeof value !== "number") return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`;
  return value.toLocaleString();
}

function pct(value: number | null | undefined, digits = 0): string {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : "—";
}

function Metric({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "neutral" | "accent" | "good";
}) {
  const color =
    tone === "accent"
      ? "text-[var(--color-accent-600)]"
      : tone === "good"
        ? "text-[var(--color-risk-low-600)]"
        : "text-[var(--color-ink)]";
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-bold tabular-nums sm:text-3xl ${color}`}>{value}</p>
      {sub && <p className="mt-0.5 truncate text-[11px] text-[var(--color-ink-faint)]">{sub}</p>}
    </div>
  );
}

function StatusBadge({ deep }: { deep: boolean }) {
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
        deep
          ? "bg-[var(--color-risk-low-100)] text-[var(--color-risk-low-600)]"
          : "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]"
      }`}
    >
      {deep ? "Deep simulated" : "Identified"}
    </span>
  );
}

function Bar({ value }: { value: number | null }) {
  const width = typeof value === "number" ? Math.max(2, Math.min(100, value * 100)) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
      <div
        className="h-full rounded-full bg-[var(--color-accent-500)]"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: TaxonomyScenarioDTO }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold leading-snug text-[var(--color-ink)]">
          {scenario.name}
        </p>
        <StatusBadge deep={scenario.deeply_simulated} />
      </div>
      <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        {scenario.genai_abuse_mechanism}
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {scenario.channels.slice(0, 3).map((channel) => (
          <span
            key={channel}
            className="rounded bg-[var(--color-surface-sunken)] px-1.5 py-0.5 text-[9px] text-[var(--color-ink-muted)]"
          >
            {channel}
          </span>
        ))}
        {scenario.channels.length > 3 && (
          <span className="px-1 py-0.5 text-[9px] text-[var(--color-ink-faint)]">
            +{scenario.channels.length - 3}
          </span>
        )}
      </div>
    </>
  );

  const className =
    "block rounded-xl border bg-[var(--color-surface)] p-3 text-left transition-standard " +
    (scenario.deeply_simulated
      ? "border-[var(--color-risk-low-600)]/40 hover:border-[var(--color-risk-low-600)]"
      : "border-[var(--color-border)]");

  // Only a deeply simulated entry has a real experiment to open.
  return scenario.deeply_simulated ? (
    <Link to="/attack-lab" className={className}>
      {body}
      <p className="mt-2 text-[10px] font-semibold text-[var(--color-accent-600)]">
        Open in Attack Lab →
      </p>
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

function TaxonomySection({ taxonomy }: { taxonomy: TaxonomyDTO }) {
  const [category, setCategory] = useState<string | null>(null);
  const shown = category
    ? taxonomy.scenarios.filter((s) => s.category === category)
    : taxonomy.scenarios;
  const countByCategory = new Map<string, number>();
  for (const scenario of taxonomy.scenarios) {
    countByCategory.set(scenario.category, (countByCategory.get(scenario.category) ?? 0) + 1);
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        <Metric
          label="Attacks identified"
          value={taxonomy.total_attacks_identified ?? "—"}
          tone="accent"
        />
        <Metric label="Categories" value={taxonomy.category_count} />
        <Metric label="Channels" value={taxonomy.channel_count} />
        <Metric
          label="Deeply simulated"
          value={taxonomy.deeply_simulated ?? "—"}
          tone="good"
          sub="the rest are identified only"
        />
      </div>

      {/* Scrolls inside itself; no negative margin, so the card never
          overflows its own container at 375px. */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => setCategory(null)}
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-standard ${
            category === null
              ? "bg-[var(--color-accent-600)] text-white"
              : "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]"
          }`}
        >
          All {taxonomy.scenarios.length}
        </button>
        {taxonomy.categories.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setCategory(name === category ? null : name)}
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-standard ${
              category === name
                ? "bg-[var(--color-accent-600)] text-white"
                : "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]"
            }`}
          >
            {titleCase(name)} {countByCategory.get(name) ?? 0}
          </button>
        ))}
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((scenario) => (
          <ScenarioCard key={scenario.id} scenario={scenario} />
        ))}
      </div>

      <p className="text-[11px] leading-snug text-[var(--color-ink-faint)]">
        {taxonomy.scope_note}
      </p>
    </div>
  );
}

function FamilyCard({ family }: { family: GenerationScaleFamilyDTO }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-ink)]">
          {FAMILY_LABEL[family.attack_family] ?? titleCase(family.attack_family)}
        </p>
        {family.constraint_valid_percentage === 100 && (
          <span className="shrink-0 rounded-full bg-[var(--color-risk-low-100)] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[var(--color-risk-low-600)]">
            100% valid
          </span>
        )}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-sm font-bold tabular-nums text-[var(--color-ink)]">
            {compact(family.transactions_generated)}
          </p>
          <p className="text-[9px] uppercase tracking-wide text-[var(--color-ink-faint)]">txns</p>
        </div>
        <div>
          <p className="text-sm font-bold tabular-nums text-[var(--color-ink)]">
            {compact(family.throughput_transactions_per_second)}
          </p>
          <p className="text-[9px] uppercase tracking-wide text-[var(--color-ink-faint)]">tx/s</p>
        </div>
        <div>
          <p className="text-sm font-bold tabular-nums text-[var(--color-ink)]">
            {typeof family.fidelity_excluding_constraints === "number"
              ? family.fidelity_excluding_constraints.toFixed(2)
              : "—"}
          </p>
          <p className="text-[9px] uppercase tracking-wide text-[var(--color-ink-faint)]">
            fidelity
          </p>
        </div>
      </div>
    </div>
  );
}

function FidelityCard({ family }: { family: GenerationScaleFamilyDTO }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-ink)]">
          {FAMILY_LABEL[family.attack_family] ?? titleCase(family.attack_family)}
        </p>
        <span className="shrink-0 text-xs font-bold tabular-nums text-[var(--color-ink)]">
          {typeof family.fidelity_excluding_constraints === "number"
            ? family.fidelity_excluding_constraints.toFixed(3)
            : "—"}
        </span>
      </div>
      <div className="mt-2 space-y-2">
        {family.fidelity_components.map((group) => (
          <div key={group.group}>
            <p className="text-[9px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
              {titleCase(group.group)}
            </p>
            <div className="mt-1 space-y-1">
              {group.metrics.map((metric) => (
                <div key={metric.name}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[10px] text-[var(--color-ink-muted)]">
                      {titleCase(metric.name)}
                    </span>
                    <span className="shrink-0 text-[10px] font-semibold tabular-nums text-[var(--color-ink)]">
                      {typeof metric.score === "number" ? metric.score.toFixed(2) : "—"}
                    </span>
                  </div>
                  <Bar value={metric.score} />
                </div>
              ))}
            </div>
          </div>
        ))}
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Constraint validity
          </p>
          <div className="mt-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] text-[var(--color-ink-muted)]">
                Simulator invariants held
              </span>
              <span className="shrink-0 text-[10px] font-semibold tabular-nums text-[var(--color-risk-low-600)]">
                {pct(
                  typeof family.constraint_valid_percentage === "number"
                    ? family.constraint_valid_percentage / 100
                    : null,
                )}
              </span>
            </div>
            <Bar
              value={
                typeof family.constraint_valid_percentage === "number"
                  ? family.constraint_valid_percentage / 100
                  : null
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function ScaleSection({ scale }: { scale: GenerationScaleDTO }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        <Metric
          label="Transactions generated"
          value={compact(scale.total_transactions)}
          tone="accent"
          sub={`${scale.total_scenarios?.toLocaleString() ?? "—"} scenarios`}
        />
        <Metric
          label="Fraud-labelled"
          value={compact(scale.total_fraud_transactions)}
          sub="of the generated total"
        />
        <Metric
          label="Throughput"
          value={`${compact(scale.aggregate_throughput_transactions_per_second)}/s`}
          sub={scale.platform || undefined}
        />
        <Metric
          label="Constraint-valid"
          value={scale.all_constraints_valid ? "100%" : "—"}
          tone="good"
          sub="all 3 families"
        />
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {scale.families.map((family) => (
          <FamilyCard key={family.attack_family} family={family} />
        ))}
      </div>
    </div>
  );
}

export function FidelitySection({ scale }: { scale: GenerationScaleDTO }) {
  return (
    <div className="space-y-2.5">
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {scale.families.map((family) => (
          <FidelityCard key={family.attack_family} family={family} />
        ))}
      </div>
      <p className="text-[11px] italic leading-snug text-[var(--color-ink-faint)]">
        {scale.fidelity_caveat}
      </p>
    </div>
  );
}

function NotProduced({ what, command }: { what: string; command: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)] p-3">
      <p className="text-xs text-[var(--color-ink-muted)]">{what} has not been produced yet.</p>
      <code className="mt-1.5 block overflow-x-auto rounded bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-ink-muted)]">
        {command}
      </code>
    </div>
  );
}

export function FraudLandscape({
  landscape,
  section,
}: {
  landscape: LandscapeResponseDTO;
  section: "taxonomy" | "scale" | "fidelity";
}) {
  if (section === "taxonomy") {
    return landscape.taxonomy ? (
      <TaxonomySection taxonomy={landscape.taxonomy} />
    ) : (
      <NotProduced
        what="The breadth taxonomy"
        command="python scripts/export_attack_taxonomy.py"
      />
    );
  }
  if (!landscape.generation_scale) {
    return (
      <NotProduced
        what="The generation-scale benchmark"
        command="python scripts/run_generation_scale_benchmark.py"
      />
    );
  }
  return section === "scale" ? (
    <ScaleSection scale={landscape.generation_scale} />
  ) : (
    <FidelitySection scale={landscape.generation_scale} />
  );
}
