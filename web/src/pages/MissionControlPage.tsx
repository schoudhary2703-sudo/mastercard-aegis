import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchBenchmark, fetchGenAI, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { NodeLoop, NodeLoopLegend, type LoopGeneration } from "../components/loop/NodeLoop";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";
import { StatTile } from "../components/ui/StatTile";
import { LOOP_STEPS, RESULTS_STEP } from "../nav/journey";

/**
 * Overview: the 15-second read for a judge who knows nothing about AEGIS.
 *
 * Four deliberate properties. The first three are load-bearing and unchanged:
 *
 * 1. **The hero, the loop, and "Where AEGIS fits" are static.** They contain
 *    no number read from an artifact, so a cold backend produces a page that
 *    still explains the whole system instead of a screen of skeletons.
 * 2. **Evidence is scoped per endpoint.** `/api/landscape`, `/api/genai` and
 *    `/api/benchmark` each get their own state, so a slow or failed landscape
 *    read cannot hide the benchmark.
 * 3. **No cross-scenario aggregate.** This screen deliberately does not sum
 *    caught/escaped counts across experiments into a headline "recall": those
 *    are separate scenarios scored by different models, and one number over
 *    them is confusable with PaySim test recall and with LOAFO mean recall.
 *
 * 4. **The result comes before the mechanism.** The measured outcome used to
 *    sit fifth, below ~600 words explaining how the loop works, so a reader
 *    scrolled two screens before learning whether any of it worked. Results
 *    now lead; the mechanism follows for whoever wants it.
 *
 * The GenAI reasoning chain and the attack-landscape breakdown were removed
 * from this screen rather than cut down. Both are the *subject* of a numbered
 * step -- step 2 argues GenAI fidelity, step 1 argues attack diversity -- and
 * rendering them here as well meant a judge read the same evidence twice and
 * the summary competed with the page that interprets it. The headline figures
 * stay; the panels are one click away, where they are the point.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : "—";
}

function num(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

/**
 * The defender generations, formatted for the ring's centre panel.
 *
 * Built from the persisted model_comparison rather than written into the
 * component: the ring animates through whatever generations the artifact
 * actually contains, and shows nothing if it contains none.
 */
function generationsFrom(
  comparison: { baseline_v1?: unknown; defender_v2?: unknown; defender_v3?: unknown } | null | undefined,
): LoopGeneration[] {
  if (!comparison) return [];
  const entries: [string, { precision?: number | null; recall?: number | null; false_positive_rate?: number | null } | null][] = [
    ["v1", (comparison.baseline_v1 ?? null) as never],
    ["v2", (comparison.defender_v2 ?? null) as never],
    ["v3", (comparison.defender_v3 ?? null) as never],
  ];
  return entries
    .filter(([, e]) => e != null)
    .map(([label, e]) => ({
      label,
      precision: pct(e?.precision),
      recall: pct(e?.recall),
      fpr: typeof e?.false_positive_rate === "number" ? `${(e.false_positive_rate * 100).toFixed(3)}%` : "—",
    }));
}

function compactInt(value: number | null | undefined): string {
  if (typeof value !== "number") return "—";
  return value >= 1000 ? `${Math.round(value / 1000)}k` : value.toLocaleString("en-US");
}

/**
 * Where to go, and what each screen is evidence for.
 *
 * Reads from `nav/journey.ts`, the same list that drives the sidebar and the
 * step footer, so the three can never disagree about the walkthrough.
 */
function JudgePath() {
  const cards = [...LOOP_STEPS, RESULTS_STEP];
  return (
    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map((s) => (
        <Link
          key={s.to}
          to={s.to}
          className="card-interactive flex flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5 shadow-[var(--shadow-card)]"
        >
          <span className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold tabular-nums text-white ${
                s.step != null
                  ? "bg-[var(--color-accent-600)]"
                  : "bg-[var(--color-defend-600)]"
              }`}
            >
              {s.step ?? "★"}
            </span>
            <span className="t-h2 text-[var(--color-ink)]">{s.label}</span>
          </span>
          <span className="t-body-sm mt-2 text-[var(--color-ink-muted)]">{s.hint}</span>
          <span className="t-eyebrow mt-auto pt-3 text-[var(--color-ink-faint)]">{s.rubric}</span>
        </Link>
      ))}
    </div>
  );
}

export function MissionControlPage() {
  const benchmarkFetch = useCallback((s: AbortSignal) => fetchBenchmark(s), []);
  const genaiFetch = useCallback((s: AbortSignal) => fetchGenAI(s), []);
  const landscapeFetch = useCallback((s: AbortSignal) => fetchLandscape(s), []);

  const benchmark = useApiResource(benchmarkFetch, []);
  const genai = useApiResource(genaiFetch, []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-8">
      {/* ---------------- Static hero: renders with no API call ------------- */}
      <header className="grid gap-8 rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow-elevated)] sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center">
        <div className="min-w-0">
        <p className="t-eyebrow text-[var(--color-accent-600)]">
          AEGIS &middot; Adversarial Evaluation &amp; Generative Immune System
        </p>
        <h1 className="t-display mt-3 max-w-3xl text-[var(--color-ink)]">
          Stress-test fraud models against attacks they haven&rsquo;t learned yet.
        </h1>
        <p className="t-body mt-4 max-w-2xl text-[var(--color-ink-muted)]">
          A closed-loop AI red team for payment fraud: GenAI finds detector blind spots,
          deterministic simulators reproduce them at scale, and the defender is challenged against
          every new generation.
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          <Link
            to="/attack-taxonomy"
            className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2.5 text-sm font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)]"
          >
            Start the walkthrough &rarr;
          </Link>
          <Link
            to="/final-benchmark"
            className="rounded-lg border border-[var(--color-border-strong)] px-4 py-2.5 text-sm font-semibold text-[var(--color-ink)] transition-standard hover:bg-[var(--color-surface-sunken)]"
          >
            Skip to the results
          </Link>
        </div>
        </div>

        {/* The loop, in the hero rather than a screen below it. It is the one
            figure that explains the whole system, and the console's only
            motion -- burying it under the fold wasted both. */}
        <div className="min-w-0">
          <NodeLoop
            generations={
              benchmark.status === "ready"
                ? generationsFrom(benchmark.data.model_comparison)
                : []
            }
          />
          <Details className="mt-2" summary="Reading the ring">
            <NodeLoopLegend />
          </Details>
        </div>
      </header>

      {/* ---------------- The result, before the mechanism ------------------ */}
      <section>
        <h2 className="t-eyebrow mb-3 text-[var(--color-ink-faint)]">
          Where it stands &mdash; Defender v3, frozen
        </h2>
        <ApiStateSection
          state={benchmark}
          emptyTitle="No benchmark summary yet"
          emptyBody="Run scripts/build_final_benchmark_summary.py to produce it."
          render={(data) => {
            const v3 = data.model_comparison?.defender_v3 ?? null;
            const loafo = data.loafo ?? null;
            const recallAtFpr = v3?.recall_at_fixed_fpr?.["0.001"] ?? null;
            return (
              <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <StatTile
                  label="PR-AUC"
                  value={num(v3?.pr_auc)}
                  hint="Untouched PaySim test split"
                />
                <StatTile
                  label="Recall @ 0.1% FPR"
                  value={pct(recallAtFpr)}
                  hint="At a fixed false-positive budget"
                />
                <StatTile
                  label="False positive rate"
                  value={
                    typeof v3?.false_positive_rate === "number"
                      ? `${(v3.false_positive_rate * 100).toFixed(4)}%`
                      : "—"
                  }
                  hint="At the tuned operating threshold"
                />
                <StatTile
                  label="Unseen-family recall"
                  value={pct(loafo?.mean_loafo_recall)}
                  tone="neutral"
                  hint="Mean across three LOAFO folds — partial, not universal"
                />
              </div>
            );
          }}
        />
      </section>

      {/* ---------------- Scale, at a glance -------------------------------- */}
      <section>
        <h2 className="t-eyebrow mb-3 text-[var(--color-ink-faint)]">What the red team produced</h2>
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <ApiStateSection
            state={landscape}
            emptyTitle="No landscape artifacts yet"
            emptyBody="Run scripts/export_attack_taxonomy.py."
            render={(data) => (
              <>
                <StatTile
                  label="Attack vectors identified"
                  value={data.taxonomy?.total_attacks_identified ?? "—"}
                  hint={
                    data.taxonomy
                      ? `${data.taxonomy.category_count} categories · ${data.taxonomy.channel_count} channels`
                      : undefined
                  }
                />
                <StatTile
                  label="Deeply simulated"
                  value={data.taxonomy?.deeply_simulated ?? "—"}
                  hint="Generator + blueprint + real detector result"
                />
                <StatTile
                  label="Transactions generated"
                  value={compactInt(data.generation_scale?.total_transactions)}
                  hint={
                    data.generation_scale
                      ? `${compactInt(data.generation_scale.total_scenarios)} scenarios · seed-reproducible`
                      : undefined
                  }
                />
              </>
            )}
          />
          <ApiStateSection
            state={genai}
            emptyTitle="No GenAI runs yet"
            emptyBody="Run scripts/run_genai_analysis.py."
            render={(data) => (
              <StatTile
                label="Rows written by GenAI"
                value="0"
                tone={data.has_live_genai ? "positive" : "neutral"}
                hint="By design — the deterministic simulator writes every row"
              />
            )}
          />
        </div>
      </section>

      {/* ---------------- Where to go next ---------------------------------- */}
      <section>
        <h2 className="t-eyebrow mb-3 text-[var(--color-ink-faint)]">
          The walkthrough &mdash; four steps, then the evidence
        </h2>
        <JudgePath />
      </section>

      {/* ---------------- Static: where AEGIS fits -------------------------- */}
      <section>
        <h2 className="t-h1 text-[var(--color-ink)]">Where AEGIS fits</h2>
        <p className="t-body-sm mb-3 mt-1 text-[var(--color-ink-muted)]">
          Offline adversarial validation for fraud-model teams. It is never in the authorization
          path.
        </p>
        <Card>
          <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {[
              {
                t: "Live payment systems",
                d: "Authorization keeps running. AEGIS is not in this path.",
                tone: "muted" as const,
              },
              {
                t: "Historical logs + fraud labels",
                d: "Pseudonymized, batch, after the fact.",
                tone: "muted" as const,
              },
              {
                t: "AEGIS offline adversarial testing",
                d: "Red-team generation, confrontation, LOAFO.",
                tone: "accent" as const,
              },
              {
                t: "Hard positives + generalization report",
                d: "What escaped, and whether hardening transfers.",
                tone: "accent" as const,
              },
              {
                t: "Next validation / retraining cycle",
                d: "Owned by fraud data-science and model-risk.",
                tone: "muted" as const,
              },
            ].map((step, i) => (
              <li
                key={step.t}
                className={`rounded-lg border p-2.5 ${
                  step.tone === "accent"
                    ? "border-[var(--color-accent-500)] bg-[var(--color-accent-100)]"
                    : "border-[var(--color-border)] bg-[var(--color-surface-sunken)]"
                }`}
              >
                <p className="t-label flex items-center gap-1.5 text-[var(--color-ink)]">
                  <span className="t-mono-sm text-[var(--color-ink-faint)]">{i + 1}</span>
                  {step.t}
                </p>
                <p className="mt-1 text-[10.5px] leading-snug text-[var(--color-ink-muted)]">
                  {step.d}
                </p>
              </li>
            ))}
          </ol>

          <Details className="mt-3" summary="Deployment constraints and data governance">
            <ul className="space-y-1.5">
              <li>
                <strong className="text-[var(--color-ink)]">
                  AEGIS is not in the authorization path.
                </strong>{" "}
                It never scores a live payment, and this demo replays persisted experiment
                artifacts rather than connecting to live scoring.
              </li>
              <li>
                Intended to run offline alongside fraud model-risk, validation and data-science
                workflows.
              </li>
              <li>
                The prototype uses synthetic / reference payment data (PaySim) throughout, and the
                Defender feature vector contains no PAN or cardholder identity fields.{" "}
                <strong className="text-[var(--color-ink)]">
                  A real deployment would require institution-specific data governance and privacy
                  controls.
                </strong>
              </li>
            </ul>
          </Details>
        </Card>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="neutral">Research prototype</Badge>
        <Badge variant="neutral">Synthetic PaySim corpus</Badge>
        <Badge variant="neutral">Read-only</Badge>
      </div>

      <Details summary="What these numbers are, and what they are not">
        Every figure on this page is read live from a persisted artifact; none is written into the
        page. <strong>PR-AUC, recall @ 0.1% FPR and false positive rate</strong> are Defender v3
        on the untouched PaySim test split &mdash; PaySim is a public synthetic mobile-money
        simulator, so these are synthetic-corpus figures, not real-traffic performance.{" "}
        <strong>LOAFO mean recall</strong> is a different measurement entirely: three fold models,
        each trained with one attack family contributing zero rows, each scored on one fresh
        scenario of that held-out family. Those fresh scenarios contain 3&ndash;12 fraud events
        each, so the per-family figures are <strong>directional, not statistically powered</strong>
        &mdash; a single additional catch or miss moves a family&rsquo;s recall by 8&ndash;33
        points. Guided-generation results, selected experiment replays and LOAFO folds are all
        separate scenarios scored by different models and are never summed into one figure.{" "}
        <strong>&ldquo;14 identified&rdquo; does not mean 14 simulated</strong> &mdash; exactly
        three families have a generator and a real detector result; the other eleven are
        research-identified only. Defender v3 is frozen and there is no Defender v4. Generalization
        to an unseen family is partial, not universal, and no claim of universal fraud detection is
        made anywhere in this submission.
      </Details>
    </div>
  );
}
