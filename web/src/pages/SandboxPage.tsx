import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AttackFamilySelector } from "../components/attack/AttackFamilySelector";
import { BlueprintPanel } from "../components/attack/BlueprintPanel";
import { ActionBadge, Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { EmptyState, SkeletonRows } from "../components/ui/States";
import { StatTile } from "../components/ui/StatTile";
import { ConfusionMatrix } from "../components/evaluation/ConfusionMatrix";
import { LoopDiagram } from "../components/loop/LoopDiagram";
import { MockDataBadge } from "../components/real/RealBadge";
import { BASE_BLUEPRINTS } from "../mock/blueprints";
import { generateBatchForFamily } from "../mock/generateBatch";
import { scoreTransactions } from "../mock/mockDetector";
import { useLoop } from "../state/LoopContext";
import {
  ATTACK_FAMILIES,
  ATTACK_FAMILY_LABEL,
  type DetectorOutput,
  type Transaction,
  type TransactionBatch,
} from "../types/aegis";

/**
 * The sandbox: every simulated surface in the app, behind one door.
 *
 * Previously the browser-side mock generator, the mock detection pass and the
 * mock round counter were embedded inside Attack Studio, Live Detection,
 * Co-Evolution and Evaluation -- next to real persisted artifacts. That made
 * the single most damaging kind of ambiguity possible: a reader could not tell
 * a measured result from a client-side toy, which devalues the real numbers
 * standing beside it.
 *
 * So every mock now lives here, on a screen that is outside the numbered
 * walkthrough, banner-labelled, and reachable only from a deliberately quiet
 * link. It is kept because DEMO_FLOW.md relies on it as the fallback if the
 * API becomes unreachable mid-demo -- not as evidence.
 */

/* ---------------------------------------------------------------------------
 * Local layout shims.
 *
 * This screen was written against a richer UI kit than this branch carries
 * (no PageHeader/SectionHeader/Panel/Callout here). Rather than introduce four
 * shared primitives -- which would collide with the page components this
 * branch has just rewritten -- the sandbox composes its own from Card, so the
 * whole screen stays in one file and touches nothing else.
 * ------------------------------------------------------------------------- */

function PageHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="max-w-[62ch]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-accent-500)]">
        {eyebrow}
      </p>
      <h1 className="mt-2 text-2xl font-bold leading-tight text-[var(--color-ink)]">{title}</h1>
      {children && <p className="mt-3 text-sm text-[var(--color-ink-muted)]">{children}</p>}
    </header>
  );
}

function SectionHeader({
  eyebrow,
  title,
  actions,
  children,
}: {
  eyebrow?: string;
  title: string;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-[58ch]">
        {eyebrow && (
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-ink-faint)]">
            {eyebrow}
          </p>
        )}
        <h2 className="text-lg font-semibold text-[var(--color-ink)]">{title}</h2>
        {children && <p className="mt-1.5 text-sm text-[var(--color-ink-muted)]">{children}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

function Panel({ children }: { children: ReactNode }) {
  return <Card>{children}</Card>;
}

function Callout({
  eyebrow,
  tone = "note",
  children,
}: {
  eyebrow: string;
  tone?: "note" | "warn";
  children: ReactNode;
}) {
  const accent =
    tone === "warn" ? "var(--color-risk-medium-600)" : "var(--color-accent-500)";
  return (
    <div
      className="rounded-r-xl border border-l-2 border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-4 py-3.5"
      style={{ borderLeftColor: accent }}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: accent }}>
        {eyebrow}
      </p>
      <div className="mt-2 text-sm text-[var(--color-ink-muted)]">{children}</div>
    </div>
  );
}

let genSeed = 20260101;
let scoreSeed = 30260101;

interface ScoredRow {
  txn: Transaction;
  out: DetectorOutput;
  outcome: "caught" | "evaded" | "correct-reject" | "false-positive";
}

const OUTCOME_BADGE: Record<
  ScoredRow["outcome"],
  { variant: "risk-low" | "risk-high" | "risk-medium" | "neutral"; label: string }
> = {
  caught: { variant: "risk-low", label: "Caught" },
  evaded: { variant: "risk-high", label: "Evaded" },
  "correct-reject": { variant: "neutral", label: "Clean" },
  "false-positive": { variant: "risk-medium", label: "False alarm" },
};

function outcomeFor(txn: Transaction, out: DetectorOutput): ScoredRow["outcome"] {
  const flagged = out.recommended_action !== "approve";
  if (txn.label === 1) return flagged ? "caught" : "evaded";
  return flagged ? "false-positive" : "correct-reject";
}

const GENERATED_COLUMNS: Column<Transaction>[] = [
  {
    key: "id",
    header: "Transaction",
    render: (t) => <span className="font-mono text-xs">{t.transaction_id}</span>,
  },
  { key: "amount", header: "Amount", align: "right", render: (t) => `$${t.amount.toLocaleString()}` },
  { key: "type", header: "Type", render: (t) => t.transaction_type },
  { key: "channel", header: "Channel", render: (t) => t.channel },
  {
    key: "label",
    header: "Ground truth",
    render: (t) =>
      t.label === 1 ? <Badge variant="attack">Fraud</Badge> : <Badge variant="neutral">Legitimate</Badge>,
  },
];

const SCORED_COLUMNS: Column<ScoredRow>[] = [
  {
    key: "id",
    header: "Transaction",
    render: (r) => <span className="font-mono text-xs">{r.txn.transaction_id}</span>,
  },
  {
    key: "amount",
    header: "Amount",
    align: "right",
    render: (r) => `$${r.txn.amount.toLocaleString()}`,
  },
  {
    key: "action",
    header: "Detector action",
    render: (r) => <ActionBadge action={r.out.recommended_action} />,
  },
  {
    key: "truth",
    header: "Ground truth",
    render: (r) =>
      r.txn.label === 1 ? (
        <Badge variant="attack">Fraud</Badge>
      ) : (
        <Badge variant="neutral">Legitimate</Badge>
      ),
  },
  {
    key: "outcome",
    header: "Outcome",
    render: (r) => (
      <Badge variant={OUTCOME_BADGE[r.outcome].variant}>{OUTCOME_BADGE[r.outcome].label}</Badge>
    ),
  },
];

export function SandboxPage() {
  const [batch, setBatch] = useState<TransactionBatch | null>(null);
  const [rows, setRows] = useState<ScoredRow[] | null>(null);
  const [busy, setBusy] = useState<"generate" | "score" | null>(null);

  // The family comes from LoopContext rather than local state: `runNextRound`
  // reads the context's family, so a local copy would let the selector and the
  // mock rounds disagree about which family is being demoed.
  const { family, setFamily, rounds, runNextRound, latest, reset } = useLoop();

  function handleGenerate() {
    setBusy("generate");
    setBatch(null);
    genSeed += 1;
    const seed = genSeed;
    window.setTimeout(() => {
      setBatch(generateBatchForFamily(family, { seed, count: 30 }));
      setBusy(null);
    }, 320);
  }

  function handleScore() {
    setBusy("score");
    setRows(null);
    scoreSeed += 1;
    const seed = scoreSeed;
    window.setTimeout(() => {
      const scoredBatch = generateBatchForFamily(family, { seed, count: 40 });
      const outputs = scoreTransactions(scoredBatch.transactions, {
        modelVersion: "detector-v1-preview",
        defenderStrength: 0.55,
        seed: seed + 1,
      });
      const outMap = new Map(outputs.map((o) => [o.transaction_id, o]));
      setRows(
        scoredBatch.transactions.map((txn) => {
          const out = outMap.get(txn.transaction_id)!;
          return { txn, out, outcome: outcomeFor(txn, out) };
        }),
      );
      setBusy(null);
    }, 320);
  }

  const caught = rows?.filter((r) => r.outcome === "caught").length ?? 0;
  const evaded = rows?.filter((r) => r.outcome === "evaded").length ?? 0;
  const alertRate = rows
    ? rows.filter((r) => r.out.recommended_action !== "approve").length / rows.length
    : 0;

  return (
    <div className="space-y-10">
      <PageHeader eyebrow="Sandbox · simulated" title="A self-contained toy of the loop. None of it is evidence.">
        Everything on this screen is generated deterministically in your browser. It shares no code,
        no model and no numbers with the AEGIS pipeline, and it exists only as a fallback if the API
        becomes unreachable during a live demo.
      </PageHeader>

      <Callout eyebrow="Read this first" tone="warn">
        <p>
          Numbers here are <strong className="font-semibold text-[var(--color-ink)]">invented by a
          seeded random generator</strong>, not measured. Nothing on this page was produced by the
          XGBoost defender or the Python simulators. For the measured results, go to{" "}
          <Link to="/final-benchmark" className="font-semibold text-[var(--color-accent-500)] hover:underline">
            Results
          </Link>
          , or start the walkthrough at{" "}
          <Link to="/" className="font-semibold text-[var(--color-accent-500)] hover:underline">
            Overview
          </Link>
          .
        </p>
      </Callout>

      <section>
        <SectionHeader eyebrow="Setup" title="Pick a family. Everything below re-seeds from it.">
          Each family maps to one canonical hand-written blueprint — illustrative, not fitted to any
          real run.
        </SectionHeader>
        <Card>
          <AttackFamilySelector
            value={family}
            onChange={(f) => {
              setFamily(f);
              setBatch(null);
              setRows(null);
            }}
          />
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <BlueprintPanel blueprint={BASE_BLUEPRINTS[family]} />
        </div>

        <div className="lg:col-span-3">
          <Card>
            <CardHeader
              title="Generate a batch"
              subtitle="Deterministic mock fixture — not a trained generator."
              action={
                <div className="flex items-center gap-2">
                  <MockDataBadge />
                  <button
                    type="button"
                    onClick={handleGenerate}
                    disabled={busy !== null}
                    className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:opacity-60"
                  >
                    {busy === "generate" ? "Generating…" : "Generate"}
                  </button>
                </div>
              }
            />
            {busy === "generate" && <SkeletonRows rows={5} />}
            {busy !== "generate" && !batch && (
              <EmptyState title="No batch yet" body="Generate a batch to see mock transactions." />
            )}
            {busy !== "generate" && batch && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-muted)]">
                  <Badge variant="neutral">seed {batch.seed}</Badge>
                  <Badge variant="neutral">{batch.transactions.length} transactions</Badge>
                  <Badge variant="neutral">{batch.generator_name}</Badge>
                </div>
                <DataTable
                  columns={GENERATED_COLUMNS}
                  rows={batch.transactions}
                  rowKey={(t) => t.transaction_id}
                  maxHeight="380px"
                />
              </div>
            )}
          </Card>
        </div>
      </section>

      <section>
        <SectionHeader eyebrow="Mock scoring" title="Score a batch with a toy detector.">
          A simple threshold function stands in for the real model. Its outputs are not comparable to
          anything in Results.
        </SectionHeader>
        <Card>
          <CardHeader
            title="Mock detection pass"
            subtitle="Generates a fresh batch for the selected family and scores it in the browser."
            action={
              <div className="flex items-center gap-2">
                <MockDataBadge />
                <button
                  type="button"
                  onClick={handleScore}
                  disabled={busy !== null}
                  className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:opacity-60"
                >
                  {busy === "score" ? "Scoring…" : "Run detection"}
                </button>
              </div>
            }
          />
          {busy === "score" && <SkeletonRows rows={6} />}
          {busy !== "score" && !rows && (
            <EmptyState title="No detection run yet" body="Run detection to see mock risk scores." />
          )}
          {busy !== "score" && rows && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile label="Transactions scored" value={rows.length} />
                <StatTile label="Fraud caught" value={caught} tone="positive" />
                <StatTile label="Fraud evaded" value={evaded} tone={evaded > 0 ? "risk" : "neutral"} />
                <StatTile label="Alert rate" value={`${(alertRate * 100).toFixed(0)}%`} />
              </div>
              <DataTable
                columns={SCORED_COLUMNS}
                rows={[...rows].reverse()}
                rowKey={(r) => r.txn.transaction_id}
                maxHeight="440px"
              />
            </div>
          )}
        </Card>
      </section>

      <section>
        <SectionHeader
          eyebrow="Mock rounds"
          title="Step a toy loop and watch its numbers move."
          actions={
            rounds.length > 0 ? (
              <button
                type="button"
                onClick={reset}
                className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-ink-muted)] transition-standard hover:border-[var(--color-border-strong)] hover:text-[var(--color-ink)]"
              >
                Reset ({rounds.length})
              </button>
            ) : undefined
          }
        >
          The real hardening rounds, with their real artifacts and their real regressions, are on{" "}
          <Link to="/co-evolution" className="font-semibold text-[var(--color-accent-500)] hover:underline">
            Evolve
          </Link>
          .
        </SectionHeader>

        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <MockDataBadge />
            <button
              type="button"
              onClick={runNextRound}
              disabled={rounds.length >= 6}
              className="rounded-lg bg-[var(--color-accent-600)] px-3 py-1.5 text-xs font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {rounds.length === 0
                ? "Run round 0"
                : rounds.length >= 6
                  ? "Demo complete"
                  : `Run round ${rounds.length}`}
            </button>
            {latest && (
              <span className="text-[11px] tabular-nums text-[var(--color-ink-muted)]">
                R{latest.roundIndex} · recall {(latest.evaluation.overall.recall * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <LoopDiagram active={latest ? "retrain" : "identify"} compact />
        </Card>

        {latest && (
          <div className="mt-4 space-y-4">
            <Panel>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-[var(--color-ink)]">
                  {latest.evaluation.evaluation_id}
                </p>
                <MockDataBadge />
                <Badge variant="neutral">{latest.evaluation.protocol}</Badge>
                <Badge variant="neutral">round {latest.evaluation.round_index}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
                <StatTile
                  label="Precision"
                  value={`${(latest.evaluation.overall.precision * 100).toFixed(1)}%`}
                />
                <StatTile
                  label="Recall"
                  value={`${(latest.evaluation.overall.recall * 100).toFixed(1)}%`}
                />
                <StatTile label="F1" value={`${(latest.evaluation.overall.f1 * 100).toFixed(1)}%`} />
                <StatTile label="ROC-AUC" value={latest.evaluation.overall.roc_auc.toFixed(2)} />
                <StatTile
                  label="False positive rate"
                  value={`${(latest.evaluation.overall.fpr * 100).toFixed(1)}%`}
                />
              </div>
            </Panel>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader title="Confusion matrix" subtitle="Overall, this mock round." />
                <ConfusionMatrix counts={latest.evaluation.overall.confusion} />
              </Card>
              <Card>
                <CardHeader title="Per attack family" subtitle="Same mock metrics, scoped by family." />
                <div className="overflow-auto">
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                        <th className="py-2 pr-3">Family</th>
                        <th className="px-3 py-2 text-right">Prec</th>
                        <th className="px-3 py-2 text-right">Recall</th>
                        <th className="px-3 py-2 text-right">F1</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ATTACK_FAMILIES.map(({ id }) => {
                        const m = latest.evaluation.per_attack_family[id];
                        return (
                          <tr key={id} className="border-b border-[var(--color-border)] last:border-0">
                            <td className="py-2 pr-3 font-medium text-[var(--color-ink)]">
                              {ATTACK_FAMILY_LABEL[id]}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {(m.precision * 100).toFixed(0)}%
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {(m.recall * 100).toFixed(0)}%
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {(m.f1 * 100).toFixed(0)}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
