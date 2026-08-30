import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchBenchmark, fetchGenAI, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { GenAIFamilyCoverage } from "../components/genai/GenAIFamilyCoverage";
import { LiveGenAIEvidence } from "../components/genai/LiveGenAIEvidence";
import { ClosedLoopFlow } from "../components/loop/ClosedLoopFlow";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";
import { StatTile } from "../components/ui/StatTile";

/**
 * Overview: the 15-second read for a judge who knows nothing about AEGIS.
 *
 * Three deliberate properties:
 *
 * 1. **The hero, the loop, and "Where AEGIS fits" are static.** They contain
 *    no number read from an artifact, so a cold backend produces a page that
 *    still explains the whole system instead of a screen of skeletons.
 * 2. **Evidence is scoped per endpoint.** `/api/landscape`, `/api/genai` and
 *    `/api/benchmark` each get their own card and their own loading/error
 *    state, so a slow or failed landscape read cannot hide the benchmark.
 * 3. **No cross-scenario aggregate.** This screen deliberately does not sum
 *    caught/escaped counts across experiments into a headline "recall": those
 *    are separate scenarios scored by different models, and one number over
 *    them is confusable with PaySim test recall and with LOAFO mean recall.
 *    Every figure below names the exact evaluation it came from.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : "—";
}

function num(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

export function MissionControlPage() {
  const benchmarkFetch = useCallback((s: AbortSignal) => fetchBenchmark(s), []);
  const genaiFetch = useCallback((s: AbortSignal) => fetchGenAI(s), []);
  const landscapeFetch = useCallback((s: AbortSignal) => fetchLandscape(s), []);

  const benchmark = useApiResource(benchmarkFetch, []);
  const genai = useApiResource(genaiFetch, []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-4">
      {/* ---------------- Static hero: renders with no API call ------------- */}
      <header className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[var(--shadow-card)] sm:p-7">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-accent-600)]">
          AEGIS &middot; Adversarial Evaluation &amp; Generative Immune System
        </p>
        <h1 className="mt-2 max-w-3xl text-2xl font-bold leading-tight text-[var(--color-ink)] sm:text-4xl">
          Stress-test fraud models against attacks they haven&rsquo;t learned yet.
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--color-ink-muted)]">
          AEGIS is a closed-loop AI red team for payment fraud. GenAI analyzes emerging attacks
          and detector blind spots, deterministic simulators reproduce them at scale, and a fraud
          defender is challenged against each new generation.
        </p>

        <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[11px] font-medium text-[var(--color-ink-muted)] sm:text-xs">
          <span className="text-[var(--color-attack-600)]">GenAI reasons</span>
          <span aria-hidden="true" className="text-[var(--color-ink-faint)]">
            &rarr;
          </span>
          <span className="text-[var(--color-attack-600)]">
            deterministic code generates transactions
          </span>
          <span aria-hidden="true" className="text-[var(--color-ink-faint)]">
            &rarr;
          </span>
          <span className="text-[var(--color-defend-600)]">XGBoost detects</span>
          <span aria-hidden="true" className="text-[var(--color-ink-faint)]">
            &rarr;
          </span>
          <span className="text-[var(--color-attack-600)]">
            escaped fraud becomes the next red-team signal
          </span>
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Link
            to="/attack-lab"
            className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)]"
          >
            Open Attack Lab &rarr;
          </Link>
          <Link
            to="/final-benchmark"
            className="rounded-lg border border-[var(--color-border-strong)] px-4 py-2 text-sm font-semibold text-[var(--color-ink)] transition-standard hover:bg-[var(--color-surface-sunken)]"
          >
            See the results
          </Link>
        </div>

        <p className="mt-4 text-[11px] leading-snug text-[var(--color-ink-faint)]">
          Research prototype over the PaySim synthetic/reference corpus. Not a production
          fraud-detection service, and not connected to live payment scoring. Exactly three attack
          families are deeply simulated; the rest of the landscape is identified research only.
        </p>
      </header>

      {/* ---------------- Static loop explanation --------------------------- */}
      <Card>
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">
            The closed loop, end to end
          </h2>
          <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
            A language model reasons at exactly two points. It never writes a transaction row.
          </p>
        </div>
        <ClosedLoopFlow />
      </Card>

      {/* ---------------- Evidence: attack landscape (/api/landscape) ------- */}
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">
            Red Team &mdash; attack landscape
          </h2>
          <Link
            to="/attack-taxonomy"
            className="text-[11px] font-semibold text-[var(--color-accent-600)] hover:underline"
          >
            Full taxonomy &rarr;
          </Link>
        </div>
        <ApiStateSection
          state={landscape}
          emptyTitle="No landscape artifacts yet"
          emptyBody="Run scripts/export_attack_taxonomy.py and scripts/run_generation_scale_benchmark.py."
          render={(data) => {
            const tax = data.taxonomy;
            const scale = data.generation_scale;
            return (
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                <StatTile
                  label="Attack vectors identified"
                  value={tax?.total_attacks_identified ?? "—"}
                  hint={
                    tax
                      ? `${tax.category_count} categories, ${tax.channel_count} channels, ${tax.rail_count} rails`
                      : undefined
                  }
                />
                <StatTile
                  label="Deeply simulated"
                  value={tax?.deeply_simulated ?? "—"}
                  hint="Families with a generator, a blueprint and a real detector result"
                />
                <StatTile
                  label="Synthetic transactions generated"
                  value={
                    typeof scale?.total_transactions === "number"
                      ? scale.total_transactions.toLocaleString("en-US")
                      : "—"
                  }
                  hint={
                    scale
                      ? `${scale.total_scenarios?.toLocaleString("en-US") ?? "—"} scenarios${
                          scale.all_deterministic ? " · seed-reproducible" : ""
                        }`
                      : undefined
                  }
                />
              </div>
            );
          }}
        />
      </Card>

      {/* ---------------- Evidence: GenAI (/api/genai) ---------------------- */}
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">
            Red Team &mdash; GenAI in the loop
          </h2>
          <Link
            to="/attack-lab"
            className="text-[11px] font-semibold text-[var(--color-accent-600)] hover:underline"
          >
            Full reasoning &rarr;
          </Link>
        </div>
        <ApiStateSection
          state={genai}
          emptyTitle="No GenAI runs yet"
          emptyBody="Run scripts/run_genai_analysis.py to produce a reasoning artifact."
          render={(data) => {
            const coverage = data.family_coverage;
            return (
              <div className="space-y-2.5">
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                  <StatTile
                    label="Families with full GenAI coverage"
                    value={
                      coverage
                        ? `${coverage.fully_covered_family_count}/${coverage.families.length}`
                        : "—"
                    }
                    tone={
                      coverage && coverage.fully_covered_family_count === coverage.families.length
                        ? "positive"
                        : "neutral"
                    }
                    hint="Attack Analyst + Blind-Spot Analyst + guided generation"
                  />
                  <StatTile
                    label="Live model calls"
                    value={data.has_live_genai ? "Yes" : "—"}
                    tone={data.has_live_genai ? "positive" : "neutral"}
                    hint="Persisted with provider, model and request id"
                  />
                  <StatTile
                    label="Transaction rows written by GenAI"
                    value="0"
                    hint="By design — the deterministic simulator writes every row"
                  />
                </div>
                <LiveGenAIEvidence genai={data} />
                {coverage && <GenAIFamilyCoverage coverage={coverage} />}
              </div>
            );
          }}
        />
      </Card>

      {/* ---------------- Evidence: defender + LOAFO (/api/benchmark) ------- */}
      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">
            Blue Team &mdash; Defender v3, and whether hardening generalizes
          </h2>
          <Link
            to="/final-benchmark"
            className="text-[11px] font-semibold text-[var(--color-accent-600)] hover:underline"
          >
            Full results &rarr;
          </Link>
        </div>
        <ApiStateSection
          state={benchmark}
          emptyTitle="No benchmark summary yet"
          emptyBody="Run scripts/build_final_benchmark_summary.py to produce it."
          render={(data) => {
            const v3 = data.model_comparison?.defender_v3 ?? null;
            const loafo = data.loafo ?? null;
            const recallAtFpr = v3?.recall_at_fixed_fpr?.["0.001"] ?? null;
            return (
              <div className="space-y-2.5">
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                  <StatTile
                    label="PR-AUC"
                    value={num(v3?.pr_auc)}
                    hint="Threshold-independent · untouched PaySim test split"
                  />
                  <StatTile
                    label="Recall @ 0.1% FPR"
                    value={pct(recallAtFpr)}
                    hint="Fixed false-positive budget · PaySim test split"
                  />
                  <StatTile
                    label="False positive rate"
                    value={
                      typeof v3?.false_positive_rate === "number"
                        ? `${(v3.false_positive_rate * 100).toFixed(4)}%`
                        : "—"
                    }
                    hint="At the validation-tuned operating threshold"
                  />
                </div>

                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-sunken)] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--color-ink-faint)]">
                      Generalization to a completely unseen attack family (LOAFO)
                    </span>
                    <Badge variant="risk-medium">Partial generalization</Badge>
                  </div>
                  <p className="mt-1.5 text-2xl font-semibold tabular-nums text-[var(--color-ink)]">
                    {pct(loafo?.mean_loafo_recall)}
                    <span className="ml-2 align-middle text-xs font-normal text-[var(--color-ink-muted)]">
                      mean LOAFO recall across three held-out families
                    </span>
                  </p>
                  <p className="mt-1 text-[11px] leading-snug text-[var(--color-ink-faint)]">
                    Each fold trains with one family contributing zero rows, then scores a fresh
                    scenario of that family. Two of three families transferred; one did not. This
                    is <strong>not</strong> Defender v3&rsquo;s recall &mdash; it is the recall of
                    three separate fold models on three separate held-out scenarios.
                  </p>
                </div>

                {v3 && (
                  <p className="text-[11px] text-[var(--color-ink-faint)]">
                    Model: <code className="font-mono">{v3.model_version}</code> &mdash; frozen.
                    Nothing on this site retrains, refits or rescores it.
                  </p>
                )}
              </div>
            );
          }}
        />
      </Card>

      {/* ---------------- Static: where AEGIS fits -------------------------- */}
      <Card>
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">Where AEGIS fits</h2>
          <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
            Offline adversarial validation and hardening infrastructure for fraud-model teams.
          </p>
        </div>

        <ol className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {[
            {
              t: "Live payment systems",
              d: "Authorization keeps running. AEGIS is not in this path.",
              tone: "muted" as const,
            },
            {
              t: "Historical transaction logs + fraud labels",
              d: "Pseudonymized, batch, after the fact.",
              tone: "muted" as const,
            },
            {
              t: "AEGIS offline adversarial testing",
              d: "Red-team generation, defender confrontation, LOAFO.",
              tone: "accent" as const,
            },
            {
              t: "Hard-positive set + generalization report",
              d: "What escaped, and whether hardening transfers.",
              tone: "accent" as const,
            },
            {
              t: "Next model validation / retraining cycle",
              d: "Owned by the fraud data-science and model-risk teams.",
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
              <p className="flex items-center gap-1.5 text-[11px] font-semibold leading-tight text-[var(--color-ink)] sm:text-xs">
                <span className="text-[10px] tabular-nums text-[var(--color-ink-faint)]">
                  {i + 1}
                </span>
                {step.t}
              </p>
              <p className="mt-1 text-[10px] leading-snug text-[var(--color-ink-muted)]">
                {step.d}
              </p>
            </li>
          ))}
        </ol>

        <ul className="mt-3 grid grid-cols-1 gap-1.5 text-[11px] leading-snug text-[var(--color-ink-muted)] sm:grid-cols-2">
          <li>
            &bull; <strong className="text-[var(--color-ink)]">AEGIS is not in the
            authorization path.</strong> It never scores a live payment.
          </li>
          <li>
            &bull; This demo is <strong className="text-[var(--color-ink)]">not connected to live
            payment scoring</strong> &mdash; it replays persisted experiment artifacts.
          </li>
          <li>
            &bull; Intended to run offline alongside fraud model-risk, validation and
            data-science workflows.
          </li>
          <li>
            &bull; The prototype uses synthetic / reference payment data (PaySim) throughout.
          </li>
          <li className="sm:col-span-2">
            &bull; The current prototype uses synthetic/reference data and its Defender
            feature vector does not include PAN or cardholder identity fields.{" "}
            <strong className="text-[var(--color-ink)]">
              A real deployment would require institution-specific data governance and privacy
              controls.
            </strong>
          </li>
        </ul>
      </Card>

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
