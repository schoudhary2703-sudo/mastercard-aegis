import { useCallback, useState } from "react";
import { fetchAttacks } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { PageHeader } from "../components/ui/PageHeader";
import { AttackFamilySelector } from "../components/attack/AttackFamilySelector";
import { BlueprintPanel } from "../components/attack/BlueprintPanel";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { EmptyState, SkeletonRows } from "../components/ui/States";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { MockDataBadge, RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";
import { BASE_BLUEPRINTS } from "../mock/blueprints";
import { generateBatchForFamily } from "../mock/generateBatch";
import type { AttackFamily, Transaction, TransactionBatch } from "../types/aegis";

let seedCounter = 20260101;

const COLUMNS: Column<Transaction>[] = [
  { key: "id", header: "Transaction", render: (t) => <span className="font-mono text-xs">{t.transaction_id}</span> },
  { key: "amount", header: "Amount", align: "right", render: (t) => `$${t.amount.toLocaleString()}` },
  { key: "type", header: "Type", render: (t) => t.transaction_type },
  { key: "channel", header: "Channel", render: (t) => t.channel },
  {
    key: "label",
    header: "Ground truth",
    render: (t) => (t.label === 1 ? <Badge variant="attack">Fraud</Badge> : <Badge variant="neutral">Legitimate</Badge>),
  },
];

export function AttackStudioPage() {
  const [family, setFamily] = useState<AttackFamily>("synthetic_identity_bustout");
  const [batch, setBatch] = useState<TransactionBatch | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);

  const blueprint = BASE_BLUEPRINTS[family];

  function handleGenerate() {
    setIsGenerating(true);
    setBatch(null);
    seedCounter += 1;
    const seed = seedCounter;
    window.setTimeout(() => {
      setBatch(generateBatchForFamily(family, { seed, count: 30 }));
      setIsGenerating(false);
    }, 380);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Studio · simulated demo"
        title="A self-contained toy of the loop, for when the API is unreachable."
      >
        Deterministic, client-side, and clearly labelled. It shares no code and no numbers with the
        real pipeline.
      </PageHeader>

      <Card>
        <CardHeader title="1. Select an attack family" subtitle="Each family maps to one canonical blueprint." />
        <AttackFamilySelector
          value={family}
          onChange={(f) => {
            setFamily(f);
            setBatch(null);
          }}
        />
      </Card>

      <Card>
        <CardHeader
          title="Real persisted attacks for this family"
          subtitle="Blueprints the pipeline has actually generated and, where confronted, scored -- filtered to the family selected above."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={attacksState}
          emptyTitle="No real attacks yet"
          emptyBody="Run scripts/run_bustout_confrontation.py or scripts/run_adaptive_bustout_round.py to populate this list."
          render={(data) => {
            const filtered = data.attacks.filter((a) => a.attack_family === family);
            return filtered.length === 0 ? (
              <p className="text-sm text-[var(--color-ink-faint)]">
                No real attacks recorded yet for this family.
              </p>
            ) : (
              <RealAttackExplorer attacks={filtered} />
            );
          }}
        />
      </Card>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">
            Interactive mock generator (simulated, not a trained generator)
          </h2>
          <MockDataBadge />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <BlueprintPanel blueprint={blueprint} />
        </div>

        <div className="lg:col-span-3">
          <Card>
            <CardHeader
              title="2. Generate an attack batch"
              subtitle="Deterministic mock fixture -- not a trained generator."
              action={
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:opacity-60"
                >
                  {isGenerating ? "Generating…" : "Generate batch"}
                </button>
              }
            />

            {isGenerating && <SkeletonRows rows={5} />}

            {!isGenerating && !batch && (
              <EmptyState title="No batch yet" body="Generate a batch to see mock transactions for this family." />
            )}

            {!isGenerating && batch && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-muted)]">
                  <Badge variant="neutral">seed {batch.seed}</Badge>
                  <Badge variant="neutral">{batch.transactions.length} transactions</Badge>
                  <Badge variant="neutral">{batch.generator_name}</Badge>
                </div>
                <DataTable columns={COLUMNS} rows={batch.transactions} rowKey={(t) => t.transaction_id} maxHeight="420px" />
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
