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
import { NodeLoop, NodeLoopLegend } from "../components/loop/NodeLoop";
import { Callout, Panel } from "../components/ui/Panel";
import { PageHeader, SectionHeader } from "../components/ui/PageHeader";
import { Reveal } from "../components/ui/Reveal";
import { StatBlock } from "../components/ui/StatBlock";

/**
 * Mission Control: the 60-second read.
 *
 * The closed loop is the hero -- it is the whole idea in one figure. Below it,
 * four measured results, then the live evidence that the loop actually ran,
 * then the caveats. Nothing on this screen is a number without a source.
 */

const pct1 = (n: number) => `${n.toFixed(1)}%`;
const pct3 = (n: number) => `${n.toFixed(3)}%`;
const pct0 = (n: number) => `${n.toFixed(0)}%`;

const V3_SOURCE = "models/xgboost-hardened-crossfamily-20260301/regression_vs_v1_v2.json";

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
  const taxonomy = landscape.status === "ready" ? landscape.data.taxonomy : null;
  const scale = landscape.status === "ready" ? landscape.data.generation_scale : null;

  return (
    <div className="space-y-14">
      {/* ---- Hero: the idea, and the figure that carries it ---------------- */}
      <section className="grid gap-8 lg:grid-cols-12 lg:items-center lg:gap-10">
        <div className="lg:col-span-6 xl:col-span-6">
          <PageHeader
            eyebrow="Command center"
            title="A fraud detector that gets harder to evade every time the red team moves."
            actions={undefined}
          >
            AEGIS runs a closed adversarial loop over synthetic payment traffic: GenAI proposes an
            attack, a deterministic simulator builds it, the detector scores it, and everything that
            slipped through becomes training data for the next generation.
          </PageHeader>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/final-benchmark"
              className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2.5 text-sm font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)]"
            >
              See the evidence →
            </Link>
            <Link
              to="/attack-lab"
              className="rounded-lg border border-[var(--color-border-strong)] px-4 py-2.5 text-sm font-medium text-[var(--color-ink)] transition-standard hover:bg-[var(--color-surface)]"
            >
              Watch a campaign run
            </Link>
          </div>
        </div>

        <div className="lg:col-span-6 xl:col-span-6">
          <Panel variant="hero">
            <NodeLoop />
          </Panel>
        </div>
      </section>

      {/* ---- Headline results --------------------------------------------- */}
      <Reveal>
        <section>
          <SectionHeader
            eyebrow="Where it stands"
            title="Defender v3, measured on a PaySim test split it never trained on."
          />
          <Panel>
            <ApiStateSection
              state={benchmark}
              emptyTitle="No benchmark data yet"
              emptyBody="Point AEGIS_ARTIFACTS_ROOT at a bundle containing models/ and data/."
              render={(data) => {
                const v3 = data.model_comparison?.defender_v3 ?? null;
                const loafo = data.loafo;
                return (
                  <div className="grid gap-7 sm:grid-cols-2 xl:grid-cols-4">
                    <StatBlock
                      label="Precision"
                      value={v3?.precision != null ? v3.precision * 100 : null}
                      format={pct1}
                      size="xl"
                      meaning="Of everything it flagged, this share was really fraud."
                      source={V3_SOURCE}
                    />
                    <StatBlock
                      label="Recall"
                      value={v3?.recall != null ? v3.recall * 100 : null}
                      format={pct1}
                      size="xl"
                      meaning="Of all real fraud, this share was caught."
                      source={V3_SOURCE}
                    />
                    <StatBlock
                      label="False positive rate"
                      value={
                        v3?.false_positive_rate != null ? v3.false_positive_rate * 100 : null
                      }
                      format={pct3}
                      size="xl"
                      tone="good"
                      meaning="≈220 false alerts per million legitimate payments."
                      source={V3_SOURCE}
                    />
                    <StatBlock
                      label="Unseen-family recall"
                      value={
                        loafo?.mean_loafo_recall != null ? loafo.mean_loafo_recall * 100 : null
                      }
                      format={pct0}
                      size="xl"
                      tone="accent"
                      meaning="Mean across three leave-one-family-out folds — partial, not universal."
                      source={loafo?.source_artifact}
                    />
                  </div>
                );
              }}
            />
          </Panel>
        </section>
      </Reveal>

      {/* ---- Loop legend + scale ------------------------------------------ */}
      <Reveal>
        <section className="grid gap-5 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <Panel className="h-full">
              <p className="t-eyebrow mb-4 text-[var(--color-ink-faint)]">Reading the loop</p>
              <NodeLoopLegend />
            </Panel>
          </div>
          <div className="lg:col-span-5">
            <Panel className="h-full">
              <p className="t-eyebrow mb-5 text-[var(--color-ink-faint)]">Pipeline scale</p>
              <div className="grid grid-cols-2 gap-6">
                <StatBlock
                  label="Attacks identified"
                  display={taxonomy?.total_attacks_identified ?? "—"}
                  meaning={`${taxonomy?.deeply_simulated ?? "—"} deeply simulated`}
                />
                <StatBlock
                  label="Transactions"
                  display={
                    typeof scale?.total_transactions === "number"
                      ? `${(scale.total_transactions / 1000).toFixed(0)}k`
                      : "—"
                  }
                  meaning={
                    typeof scale?.aggregate_throughput_transactions_per_second === "number"
                      ? `${(scale.aggregate_throughput_transactions_per_second / 1000).toFixed(1)}k/sec generated`
                      : undefined
                  }
                />
                <StatBlock
                  label="Current defender"
                  display={current ? "v3" : "—"}
                  meaning={current?.model_version}
                />
                <ApiStateSection
                  state={experiments}
                  emptyTitle="No experiments yet"
                  emptyBody="Run a confrontation to populate this."
                  render={(data) => {
                    const t = totals(data.experiments);
                    return (
                      <StatBlock
                        label="Fresh scenarios"
                        display={`${t.caught}/${t.fraud}`}
                        tone={t.fraud > 0 && t.caught / t.fraud >= 0.5 ? "good" : "bad"}
                        meaning="caught by v3 on unseen scenarios"
                      />
                    );
                  }}
                />
              </div>
            </Panel>
          </div>
        </section>
      </Reveal>

      {/* ---- Proof the loop actually ran ---------------------------------- */}
      <Reveal>
        <section>
          <SectionHeader
            eyebrow="The loop, on the record"
            title="GenAI reasoning is persisted, timestamped, and never produces a number."
            actions={
              <Link
                to="/attack-lab"
                className="t-body-sm font-semibold text-[var(--color-accent-500)] hover:text-[var(--color-ink)]"
              >
                Full reasoning →
              </Link>
            }
          >
            Each run stores the analyst's read of the detector, the bounded mutation it proposed, and
            the deterministic outcome that followed.
          </SectionHeader>
          <Panel>
            <ApiStateSection
              state={genai}
              emptyTitle="No GenAI runs yet"
              emptyBody="Run scripts/run_genai_analysis.py to produce a reasoning artifact."
              render={(data) => (
                <div className="space-y-4">
                  <LiveGenAIEvidence genai={data} />
                  {data.family_coverage && <GenAIFamilyCoverage coverage={data.family_coverage} />}
                </div>
              )}
            />
          </Panel>
        </section>
      </Reveal>

      <Reveal>
        <Callout eyebrow="How to read this">
          Fresh-scenario counts are <strong className="font-semibold text-[var(--color-ink)]">Defender v3</strong>{" "}
          on one previously-unseen scenario per family — real persisted transactions, but only 3–12
          fraud events each, so they are directional, not a statistically powered sample. They are
          deliberately not mixed with the LOAFO fold models, which had a family withheld from
          training and score far worse by design; those appear in Final Results, labelled. Precision,
          recall and FPR are Defender v3 on the untouched PaySim test split. Generalization to a
          completely unseen family is partial, not universal. This is a bounded research loop over
          synthetic PaySim data — no real customer or card data anywhere.
        </Callout>
      </Reveal>
    </div>
  );
}
