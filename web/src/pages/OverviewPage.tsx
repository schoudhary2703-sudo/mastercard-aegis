import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchOverview } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/States";
import { StatTile } from "../components/ui/StatTile";
import { LoopDiagram } from "../components/loop/LoopDiagram";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { MockDataBadge, RealDataBadge } from "../components/real/RealBadge";
import { RealOverviewPanel } from "../components/real/RealOverviewPanel";
import { useLoop } from "../state/LoopContext";
import { ATTACK_FAMILY_LABEL } from "../types/aegis";

const NAV_CARDS = [
  { to: "/attack-studio", title: "Attack Studio", body: "Pick a family and generate a synthetic attack batch." },
  { to: "/live-detection", title: "Live Detection", body: "Per-transaction risk scores, caught vs. evaded." },
  { to: "/co-evolution", title: "Co-Evolution", body: "Run the closed loop round over round. The hero demo." },
  { to: "/attack-taxonomy", title: "Attack Taxonomy", body: "The three in-scope families and their blueprints." },
  { to: "/evaluation", title: "Evaluation", body: "Protocol-scoped metrics for the current round." },
  {
    to: "/final-benchmark",
    title: "Final Benchmark",
    body: "v1 vs v2 vs v3, LOAFO generalization, and the hardest surviving attacks.",
  },
];

export function OverviewPage() {
  const { rounds, latest, family } = useLoop();
  const overviewFetch = useCallback((signal: AbortSignal) => fetchOverview(signal), []);
  const overviewState = useApiResource(overviewFetch, []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Real pipeline status"
          subtitle="What the AEGIS red/blue pipeline has actually produced on disk, read live through the API."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={overviewState}
          emptyTitle="No pipeline artifacts yet"
          emptyBody="Run scripts/train_baseline_detector.py and scripts/run_bustout_confrontation.py to populate this view."
          render={(overview) => <RealOverviewPanel overview={overview} />}
        />
      </Card>

      <Card>
        <CardHeader
          title="The closed loop (interactive demo)"
          subtitle="A Red Team invents and mutates fraud; a Blue Team detects it; the loop feeds successful evasions back as training signal."
          action={<MockDataBadge />}
        />
        <LoopDiagram active={latest ? "retrain" : undefined} />
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Attack families in scope" value="3" hint="Deliberately fixed, not extensible." />
        <StatTile
          label="Rounds run this session"
          value={rounds.length}
          hint={rounds.length === 0 ? "Start in Co-Evolution" : `Family: ${ATTACK_FAMILY_LABEL[family]}`}
        />
        <StatTile
          label="Current model version"
          value={latest ? latest.modelVersion : "—"}
          tone={latest ? "positive" : "neutral"}
        />
        <StatTile
          label="Latest recall"
          value={latest ? `${(latest.evaluation.overall.recall * 100).toFixed(0)}%` : "—"}
          delta={
            rounds.length > 1
              ? {
                  direction:
                    rounds[rounds.length - 1].evaluation.overall.recall >= rounds[rounds.length - 2].evaluation.overall.recall
                      ? "up"
                      : "down",
                  label: "vs. previous round",
                }
              : undefined
          }
        />
      </div>

      {rounds.length === 0 && (
        <EmptyState
          title="No rounds run yet"
          body="This demo is entirely local and mocked. Head to Co-Evolution to generate an attack, score it, and watch the defender adapt round over round."
          action={
            <Link
              to="/co-evolution"
              className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)]"
            >
              Start Co-Evolution
            </Link>
          }
        />
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Explore the system</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          {NAV_CARDS.map((c) => (
            <Link key={c.to} to={c.to} className="block">
              <Card className="h-full transition-standard hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-elevated)]">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-[var(--color-ink)]">{c.title}</p>
                  {c.to === "/co-evolution" && <Badge variant="defend">Hero</Badge>}
                </div>
                <p className="mt-1.5 text-xs text-[var(--color-ink-muted)]">{c.body}</p>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
