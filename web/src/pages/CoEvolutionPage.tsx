import { useState } from "react";
import { AttackFamilySelector } from "../components/attack/AttackFamilySelector";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { EmptyState } from "../components/ui/States";
import { StatTile } from "../components/ui/StatTile";
import { Tabs } from "../components/ui/Tabs";
import { LoopDiagram } from "../components/loop/LoopDiagram";
import { EvasionFeedbackPanel } from "../components/evolution/EvasionFeedbackPanel";
import { MetricsTrendChart } from "../components/evolution/MetricsTrendChart";
import { RoundStepper } from "../components/evolution/RoundStepper";
import type { RoundRecord } from "../mock/loopSimulator";
import { useLoop } from "../state/LoopContext";

type DetailTab = "summary" | "feedback";

const METRIC_COLUMNS: Column<RoundRecord>[] = [
  { key: "round", header: "Round", render: (r) => <span className="font-semibold">R{r.roundIndex}</span> },
  { key: "model", header: "Model version", render: (r) => <span className="font-mono text-xs">{r.modelVersion}</span> },
  { key: "recall", header: "Recall", align: "right", render: (r) => `${(r.evaluation.overall.recall * 100).toFixed(0)}%` },
  { key: "precision", header: "Precision", align: "right", render: (r) => `${(r.evaluation.overall.precision * 100).toFixed(0)}%` },
  { key: "alert", header: "Alert rate", align: "right", render: (r) => `${(r.evaluation.overall.alert_rate * 100).toFixed(0)}%` },
  {
    key: "evaded",
    header: "Fraud evaded",
    align: "right",
    render: (r) => r.feedback.transaction_ids.length,
  },
];

export function CoEvolutionPage() {
  const { family, setFamily, rounds, runNextRound, latest } = useLoop();
  const [tab, setTab] = useState<DetailTab>("summary");

  const caught = latest ? latest.evaluation.overall.confusion.true_positive : 0;
  const evaded = latest ? latest.feedback.transaction_ids.length : 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Adversarial loop"
          subtitle="Each round: Identify -> Generate -> Defend -> Evaluate -> Evolve -> Retrain."
          action={
            <button
              type="button"
              onClick={runNextRound}
              disabled={rounds.length >= 6}
              className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {rounds.length === 0 ? "Run round 0" : rounds.length >= 6 ? "Demo complete" : `Run round ${rounds.length}`}
            </button>
          }
        />
        <LoopDiagram active={latest ? "retrain" : "identify"} compact />
        <div className="mt-5">
          <AttackFamilySelector value={family} onChange={setFamily} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Round progress" subtitle="Up to 6 rounds per demo run." />
        <RoundStepper rounds={rounds} activeIndex={rounds.length} />
      </Card>

      {!latest && (
        <EmptyState
          title="Run the first round"
          body="Generates an attack batch, scores it with the current detector, evaluates the result, and derives feedback for the next generation."
        />
      )}

      {latest && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile label="Current round" value={`R${latest.roundIndex}`} />
            <StatTile label="Model version" value={latest.modelVersion} />
            <StatTile label="Fraud caught" value={caught} tone="positive" />
            <StatTile label="Fraud evaded" value={evaded} tone={evaded > 0 ? "risk" : "neutral"} />
          </div>

          <Card>
            <CardHeader title="Round-over-round metrics" subtitle="Recall should rise as the fraud evasion rate falls." />
            <MetricsTrendChart rounds={rounds} />
          </Card>

          <Card>
            <CardHeader
              title={`Round ${latest.roundIndex} detail`}
              subtitle={`Generation ${latest.generation} · blueprint ${latest.blueprint.attack_id}`}
              action={
                <Tabs
                  options={[
                    { value: "summary", label: "Summary" },
                    { value: "feedback", label: "Evasion feedback" },
                  ]}
                  value={tab}
                  onChange={setTab}
                />
              }
            />

            {tab === "summary" ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="attack">{latest.batch.transactions.length} transactions generated</Badge>
                <Badge variant="defend">Detector {latest.modelVersion}</Badge>
                <Badge variant={latest.feedback.evaded ? "risk-high" : "risk-low"}>
                  {latest.feedback.evaded ? "Attack found an evasion" : "Attack fully caught"}
                </Badge>
                <Badge variant="neutral">Defender strength dial: {(latest.defenderStrength * 100).toFixed(0)}%</Badge>
              </div>
            ) : (
              <EvasionFeedbackPanel feedback={latest.feedback} />
            )}
          </Card>

          <Card padded={false}>
            <div className="p-5 pb-0">
              <CardHeader title="All rounds" subtitle="Every round run this session, most recent last." />
            </div>
            <div className="px-5 pb-5">
              <DataTable columns={METRIC_COLUMNS} rows={rounds} rowKey={(r) => `${r.roundIndex}`} />
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
