import type { FamilyCoverageDTO, GenAIFamilySummaryDTO } from "../../api/types";

/**
 * GenAI coverage across the three deeply simulated families, one row each.
 *
 *   Synthetic Identity   LIVE GENAI ✓   mutation → scenario → caught/escaped
 *   Mule Network         — with the reason it is missing
 *
 * `available` is server-computed and means live AND schema-valid, so a
 * recorded replay never earns a ✓. A missing stage shows its reason rather
 * than a blank, which is what keeps a gap visible instead of ambiguous.
 */

function pct(value: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "—";
}

function Tick({ ok }: { ok: boolean }) {
  return (
    <span
      className={
        ok
          ? "font-bold text-[var(--color-risk-low-600)]"
          : "text-[var(--color-ink-faint)]"
      }
      aria-label={ok ? "available" : "not available"}
    >
      {ok ? "✓" : "—"}
    </span>
  );
}

function FamilyRow({ family }: { family: FamilyCoverageDTO }) {
  const guided = family.guided_generation;
  return (
    <div className="border-t border-[var(--color-border)] px-3 py-2 first:border-t-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="min-w-[8.5rem] text-xs font-semibold text-[var(--color-ink)]">
          {family.label}
        </span>
        <span className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)]">
          <span className="flex items-center gap-1">
            Attack <Tick ok={family.attack_analyst.available} />
          </span>
          <span className="flex items-center gap-1">
            Blind spot <Tick ok={family.blind_spot_analyst.available} />
          </span>
          <span className="flex items-center gap-1">
            Guided <Tick ok={guided.available} />
          </span>
        </span>
        {family.has_live_genai && (
          <span className="rounded-full bg-[var(--color-risk-low-100)] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[var(--color-risk-low-600)]">
            Live GenAI
          </span>
        )}
      </div>

      {guided.available ? (
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11px] tabular-nums text-[var(--color-ink-muted)]">
          <span className="font-mono">
            {guided.applied_mutation_count} mutation
            {guided.applied_mutation_count === 1 ? "" : "s"}
            {guided.rejected_mutation_count > 0 && ` · ${guided.rejected_mutation_count} rejected`}
          </span>
          <span className="break-all font-mono text-[var(--color-ink)]">{guided.scenario_id}</span>
          <span>
            <span className="font-semibold text-[var(--color-risk-low-600)]">
              {guided.caught_count} caught
            </span>
            {" · "}
            <span className="font-semibold text-[var(--color-risk-high-600)]">
              {guided.escaped_count} escaped
            </span>
            {" · recall "}
            {pct(guided.recall)}
            {" · fidelity "}
            {typeof guided.fidelity_score === "number" ? guided.fidelity_score.toFixed(2) : "—"}
            {typeof guided.runtime_seconds === "number" &&
              ` · ${guided.runtime_seconds.toFixed(2)}s`}
          </span>
        </div>
      ) : (
        <p className="mt-1 text-[11px] text-[var(--color-ink-faint)]">
          {guided.reason || family.blind_spot_analyst.reason}
        </p>
      )}
    </div>
  );
}

export function GenAIFamilyCoverage({ coverage }: { coverage: GenAIFamilySummaryDTO }) {
  if (coverage.families.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--color-surface-sunken)] px-3 py-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
          GenAI family coverage
        </span>
        <span className="text-[10px] text-[var(--color-ink-muted)]">
          <span className="font-semibold text-[var(--color-ink)]">
            {coverage.live_family_count}/{coverage.families.length}
          </span>{" "}
          live · {coverage.guided_family_count}/{coverage.families.length} guided
        </span>
      </div>
      {coverage.families.map((family) => (
        <FamilyRow key={family.attack_family} family={family} />
      ))}
    </div>
  );
}
