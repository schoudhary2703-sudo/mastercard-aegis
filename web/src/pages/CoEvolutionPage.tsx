import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchEvolution, fetchExperiments } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { ExperimentDTO } from "../api/types";
import { OutcomeBadge } from "../components/lab/ReplayStream";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealEvolutionTimeline } from "../components/real/RealEvolutionTimeline";
import { Card } from "../components/ui/Card";

/**
 * Evolution answers one question: *what happened during the loop?*
 *
 * It is deliberately not a second Results page. Generalization evidence
 * (LOAFO, the model-comparison table, the full hardest-survivor ranking) lives
 * on Results and is linked to from here rather than repeated.
 *
 * Scenario-identity rule, which drives the wording throughout:
 *
 *  * A core-only family (bust-out) has one confrontation artifact *per
 *    defender generation*, each with its own scenario id -- same blueprint,
 *    three different scenario instances. Those are recorded snapshots, NOT a
 *    same-scenario v1 -> v2 -> v3 comparison, and must never be drawn as a
 *    causal chart.
 *  * A LOAFO family (mule, adaptive) has one fold report holding exactly one
 *    fresh scenario, scored by both the fold model and Defender v3. That one
 *    *is* same-scenario, and `loafo_summary.json`'s methodology says so.
 *
 * The copy follows `progression[].role` rather than assuming either case.
 */

/** Roles that mean "this row is a core defender generation", not a fold model. */
const CORE_ROLES = new Set(["baseline_v1", "defender_v2", "defender_v3"]);

function FamilyHistory({ experiment }: { experiment: ExperimentDTO }) {
  const coreOnly = experiment.progression.every((p) => CORE_ROLES.has(p.role));

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-ink)]">{experiment.label}</p>
        <div className="flex flex-wrap items-center gap-2 text-[11px] tabular-nums">
          <span className="text-[var(--color-risk-low-600)]">
            {experiment.current_defender?.caught_count ?? experiment.caught_count} caught
          </span>
          <span className="text-[var(--color-ink-faint)]">·</span>
          <span className="text-[var(--color-risk-high-600)]">
            {experiment.current_defender?.escaped_count ?? experiment.escaped_count} escaped
          </span>
          <span className="text-[var(--color-ink-faint)]">by Defender v3</span>
        </div>
      </div>

      <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {coreOnly ? "Recorded hardening snapshots" : "Held-out fold vs Defender v3"}
      </p>

      <div className="mt-1.5 space-y-1.5">
        {experiment.progression.map((p) => (
          <div key={p.label + p.model_version} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-[11px] text-[var(--color-ink-muted)] sm:w-44">
              {p.label}
            </span>
            <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--color-border)]">
              <div
                className="h-full rounded-full bg-[var(--color-risk-low-600)]"
                style={{ width: `${Math.max(1, p.recall * 100)}%` }}
              />
            </div>
            <span className="w-14 shrink-0 text-right text-[11px] font-semibold tabular-nums text-[var(--color-ink)]">
              {p.caught_count}/{p.fraud_count}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-1.5 text-[10px] leading-snug text-[var(--color-ink-faint)]">
        {coreOnly
          ? "One confrontation was recorded per defender generation against the same blueprint, each with its own persisted scenario. These document the system's evolution — they are not automatically same-scenario model comparisons."
          : "Both rows were scored on the same fresh held-out scenario."}
      </p>

      {experiment.hardest_survivor && (
        <div className="mt-2.5 border-t border-[var(--color-border)] pt-2">
          <div className="flex flex-wrap items-center gap-2">
            <OutcomeBadge caught={false} />
            <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-[var(--color-ink-muted)]">
              {experiment.hardest_survivor.transaction_id}
            </span>
            <span className="shrink-0 text-[11px] font-semibold tabular-nums text-[var(--color-ink)]">
              {(experiment.hardest_survivor.detector_risk_score * 100).toFixed(1)}% risk
            </span>
          </div>
          {/* Role is read from the artifact this row came from, never inferred
              from caught/escaped status. A confrontation escape *may* have been
              promoted; a LOAFO fold escape is evaluation evidence and never
              feeds training. Neither is asserted as promoted here. */}
          <p className="mt-1 text-[10px] leading-snug text-[var(--color-ink-faint)]">
            {coreOnly
              ? "Recorded escape — exposes a blind spot. May inform hardening when promoted as a hard positive."
              : "LOAFO evaluation evidence — exposes a blind spot. Evaluation only; does not imply retraining."}
          </p>
        </div>
      )}
    </div>
  );
}

function EscapeSummary({ experiments }: { experiments: ExperimentDTO[] }) {
  // Current-defender counters, not the per-experiment headline: a LOAFO
  // family's headline describes the handicapped fold model, so summing those
  // would report an escape count no deployed defender actually produces.
  const totalEscaped = experiments.reduce(
    (n, e) => n + (e.current_defender?.escaped_count ?? 0),
    0,
  );
  const totalFraud = experiments.reduce((n, e) => n + (e.current_defender?.fraud_count ?? 0), 0);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Fraud attempts
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-ink)]">
            {totalFraud}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-risk-high-100)] bg-[var(--color-risk-high-100)]/40 p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Escaped
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-risk-high-600)]">
            {totalEscaped}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-risk-low-100)] bg-[var(--color-risk-low-100)]/40 p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Caught
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-risk-low-600)]">
            {totalFraud - totalEscaped}
          </p>
        </div>
      </div>

      <p className="text-[11px] leading-snug text-[var(--color-ink-faint)]">
        Defender v3&rsquo;s counts across each family&rsquo;s fresh scenario &mdash; 3&ndash;12
        fraud events each, so these are directional, not statistically powered.
      </p>

      <div className="space-y-2.5">
        {experiments.map((e) => (
          <FamilyHistory key={e.attack_family} experiment={e} />
        ))}
      </div>
    </div>
  );
}

export function CoEvolutionPage() {
  const evolutionFetch = useCallback((s: AbortSignal) => fetchEvolution(s), []);
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);

  const evolution = useApiResource(evolutionFetch, []);
  const experiments = useApiResource(experimentsFetch, [], (d) => d.experiments.length === 0);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Evolution</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          What happened during the red-team / blue-team loop.
        </p>
      </header>

      <Card>
        <p className="text-sm leading-relaxed text-[var(--color-ink)]">
          AEGIS records how attacks expose detector blind spots and how those failures feed the
          next hardening cycle.
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] font-medium text-[var(--color-ink-muted)]">
          {[
            "attack generated",
            "Defender misses fraud",
            "escapes expose blind spots",
            "promoted escapes harden the defender",
            "next confrontation",
            "GenAI proposes a bounded next generation",
          ].map((step, i, all) => (
            <span key={step} className="inline-flex items-center gap-1.5">
              <span className={i % 2 === 0 ? "text-[var(--color-attack-600)]" : "text-[var(--color-defend-600)]"}>
                {step}
              </span>
              {i < all.length - 1 && (
                <span aria-hidden="true" className="text-[var(--color-ink-faint)]">
                  &rarr;
                </span>
              )}
            </span>
          ))}
        </p>
        <p className="mt-2 text-[11px] leading-snug text-[var(--color-ink-faint)]">
          This is a record of what the loop did, not a claim that each cycle improved the
          detector. Whether the hardening actually generalized is answered on{" "}
          <Link
            to="/final-benchmark"
            className="font-semibold text-[var(--color-accent-600)] hover:underline"
          >
            Results
          </Link>
          .
        </p>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Closed-loop timeline</h2>
        <ApiStateSection
          state={evolution}
          emptyTitle="No closed-loop artifacts yet"
          emptyBody="Run the pipeline scripts to populate this timeline."
          render={(data) => <RealEvolutionTimeline evolution={data} />}
        />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-[var(--color-ink)]">
          What escaped, per attack family
        </h2>
        <p className="mb-3 mt-0.5 text-xs leading-snug text-[var(--color-ink-muted)]">
          Recorded escapes reveal detector blind spots. Where the persisted experiment promoted
          them as hard positives, they informed a later hardening round.{" "}
          <strong className="text-[var(--color-ink)]">
            LOAFO entries are evaluation evidence only and do not imply retraining.
          </strong>
        </p>
        <ApiStateSection
          state={experiments}
          emptyTitle="No experiments yet"
          emptyBody="No persisted confrontation or LOAFO artifacts found."
          render={(data) => <EscapeSummary experiments={data.experiments} />}
        />
      </Card>

      <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2.5 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        The full hardest-surviving-attack ranking, the v1/v2/v3 native-test comparison and the
        LOAFO generalization benchmark all live on{" "}
        <Link
          to="/final-benchmark"
          className="font-semibold text-[var(--color-accent-600)] hover:underline"
        >
          Results
        </Link>{" "}
        so they are stated once, in the place that interprets them.
      </p>

    </div>
  );
}
