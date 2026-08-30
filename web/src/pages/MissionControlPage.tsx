import { useCallback } from "react";
import { Link } from "react-router-dom";
import {
  fetchBenchmark,
  fetchExperiments,
  fetchGenAI,
  fetchLandscape,
  fetchOverview,
} from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { ExperimentDTO } from "../api/types";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { GenAIFamilyCoverage } from "../components/genai/GenAIFamilyCoverage";
import { LiveGenAIEvidence } from "../components/genai/LiveGenAIEvidence";
import { ClosedLoopFlow } from "../components/loop/ClosedLoopFlow";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";

/**
 * Mission Control: the 30-second read.
 *
 * Everything on this screen is a number or a shape, not a paragraph. The
 * methodology that used to sit here as body text is behind the single
 * <Details> at the bottom, and the per-family story now lives in Attack Lab.
 */

function Metric({
  label,
  value,
  tone = "neutral",
  sub,
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "good" | "bad" | "accent";
  sub?: string;
}) {
  const color =
    tone === "good"
      ? "text-[var(--color-risk-low-600)]"
      : tone === "bad"
        ? "text-[var(--color-risk-high-600)]"
        : tone === "accent"
          ? "text-[var(--color-accent-600)]"
          : "text-[var(--color-ink)]";
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 sm:p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-bold tabular-nums sm:text-3xl ${color}`}>{value}</p>
      {sub && <p className="mt-0.5 truncate text-[11px] text-[var(--color-ink-faint)]">{sub}</p>}
    </div>
  );
}

/**
 * Aggregates the CURRENT defender's result per family.
 *
 * Deliberately uses `current_defender` rather than each experiment's headline
 * counters: for a LOAFO family those describe the fold model that had the
 * family withheld from training, so summing them would report a recall no
 * defender actually has.
 */
function totals(experiments: ExperimentDTO[]) {
  return experiments.reduce(
    (acc, e) => {
      const stage = e.current_defender;
      if (!stage) return acc;
      return {
        fraud: acc.fraud + stage.fraud_count,
        caught: acc.caught + stage.caught_count,
        escaped: acc.escaped + stage.escaped_count,
      };
    },
    { fraud: 0, caught: 0, escaped: 0 },
  );
}

export function MissionControlPage() {
  const overviewFetch = useCallback((s: AbortSignal) => fetchOverview(s), []);
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);
  const benchmarkFetch = useCallback((s: AbortSignal) => fetchBenchmark(s), []);
  const genaiFetch = useCallback((s: AbortSignal) => fetchGenAI(s), []);
  const landscapeFetch = useCallback((s: AbortSignal) => fetchLandscape(s), []);

  const overview = useApiResource(overviewFetch, []);
  const experiments = useApiResource(experimentsFetch, []);
  const benchmark = useApiResource(benchmarkFetch, []);
  const genai = useApiResource(genaiFetch, []);
  const landscape = useApiResource(landscapeFetch, []);

  const current = overview.status === "ready" ? overview.data.current_model : null;
  // Every headline number below comes from one of these payloads. Nothing on
  // this screen is written into the component.
  const taxonomy = landscape.status === "ready" ? landscape.data.taxonomy : null;
  const scale = landscape.status === "ready" ? landscape.data.generation_scale : null;
  const liveGenAI = genai.status === "ready" && genai.data.has_live_genai;
  const guided = genai.status === "ready" ? genai.data.latest_guided_generation : null;
  const v3 =
    benchmark.status === "ready" ? benchmark.data.model_comparison?.defender_v3 ?? null : null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Mission Control</h1>
          <p className="text-xs text-[var(--color-ink-muted)]">
            Adversarial red/blue loop over synthetic payments — all figures read live from
            persisted artifacts.
          </p>
        </div>
        <Link
          to="/attack-lab"
          className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)]"
        >
          Open Attack Lab →
        </Link>
      </header>

      <Card>
        <ApiStateSection
          state={experiments}
          emptyTitle="No experiments yet"
          emptyBody="Point AEGIS_ARTIFACTS_ROOT at a bundle containing models/ and data/."
          render={(data) => {
            const t = totals(data.experiments);
            const recall = t.fraud > 0 ? t.caught / t.fraud : 0;
            return (
              <div className="grid grid-cols-2 gap-2.5 sm:gap-3 lg:grid-cols-4">
                <Metric
                  label="Current defender"
                  value={current ? "v3" : "—"}
                  tone="accent"
                  sub={current?.model_version}
                />
                <Metric
                  label="Attacks identified"
                  value={taxonomy?.total_attacks_identified ?? "—"}
                  sub={`${taxonomy?.deeply_simulated ?? "—"} deeply simulated`}
                />
                <Metric
                  label="Transactions generated"
                  value={
                    typeof scale?.total_transactions === "number"
                      ? `${(scale.total_transactions / 1000).toFixed(0)}k`
                      : "—"
                  }
                  sub={
                    typeof scale?.aggregate_throughput_transactions_per_second === "number"
                      ? `${(scale.aggregate_throughput_transactions_per_second / 1000).toFixed(1)}k tx/s`
                      : undefined
                  }
                />
                <Metric
                  label="Live GenAI"
                  value={liveGenAI ? "Yes" : "—"}
                  tone={liveGenAI ? "good" : "neutral"}
                  sub={guided?.genai_guided ? "guided generation on disk" : "reasoning artifacts"}
                />
                <Metric label="Fraud attempts" value={t.fraud} sub="Defender v3, all families" />
                <Metric label="Caught" value={t.caught} tone="good" sub="by Defender v3" />
                <Metric label="Escaped" value={t.escaped} tone="bad" sub="by Defender v3" />
                <Metric
                  label="Recall"
                  value={`${(recall * 100).toFixed(0)}%`}
                  tone={recall >= 0.5 ? "good" : "bad"}
                  sub="on fresh scenarios"
                />
                <Metric
                  label="Test FPR"
                  value={
                    v3?.false_positive_rate != null
                      ? `${(v3.false_positive_rate * 100).toFixed(3)}%`
                      : "—"
                  }
                  sub="PaySim test split"
                />
                <Metric
                  label="Test recall"
                  value={v3?.recall != null ? `${(v3.recall * 100).toFixed(1)}%` : "—"}
                  sub="PaySim test split"
                />
              </div>
            );
          }}
        />
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">GenAI in the loop</h2>
          <Link
            to="/attack-lab"
            className="text-[11px] font-semibold text-[var(--color-accent-600)] hover:underline"
          >
            Full reasoning →
          </Link>
        </div>
        <ApiStateSection
          state={genai}
          emptyTitle="No GenAI runs yet"
          emptyBody="Run scripts/run_genai_analysis.py to produce a reasoning artifact."
          render={(data) => (
            <div className="space-y-2.5">
              <LiveGenAIEvidence genai={data} />
              {data.family_coverage && <GenAIFamilyCoverage coverage={data.family_coverage} />}
            </div>
          )}
        />
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">The closed loop</h2>
          <span className="rounded-full bg-[var(--color-defend-100)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-defend-600)]">
            Real pipeline
          </span>
        </div>
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <div className="min-w-[560px]">
            <ClosedLoopFlow />
          </div>
        </div>
      </Card>

      <Details summary="What these numbers are, and what they are not">
        Fraud / caught / escaped are <strong>Defender v3&rsquo;s</strong> results on one fresh,
        previously-unseen scenario per family — real persisted transactions, but 3–12 fraud events
        each, so they are directional, not a statistically powered sample. They are deliberately
        not mixed with the LOAFO fold models, which had a family withheld from training and score
        far worse by design; those appear in Attack Lab and Final Results, labelled. Test FPR and
        test recall are Defender v3 on the untouched PaySim test split. Generalization to a
        completely unseen family is partial, not universal. This is a bounded research loop over
        synthetic PaySim data — no real customer or card data is involved anywhere.
      </Details>
    </div>
  );
}
