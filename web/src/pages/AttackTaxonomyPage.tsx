import { useCallback } from "react";
import { fetchAttacks, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { PageHeader } from "../components/ui/PageHeader";
import { BlueprintPanel } from "../components/attack/BlueprintPanel";
import { FraudLandscape } from "../components/landscape/FraudLandscape";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { MockDataBadge, RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";
import { BASE_BLUEPRINTS } from "../mock/blueprints";
import { ATTACK_FAMILIES } from "../types/aegis";

export function AttackTaxonomyPage() {
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);
  const landscapeFetch = useCallback((signal: AbortSignal) => fetchLandscape(signal), []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Identify · attack atlas"
        title="The GenAI-enabled payment fraud surface, mapped — and the three families we simulate end to end."
      >
        Breadth is catalogued with evidence; depth is claimed only where a generator, a detector
        result, and a blueprint all exist.
      </PageHeader>

      <Card>
        <CardHeader
          title="Fraud landscape"
          subtitle="Identified across the GenAI-enabled payment threat surface. Only the three badged DEEP SIMULATED have a generator, a detector result, and a blueprint."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={landscape}
          emptyTitle="No taxonomy artifact yet"
          emptyBody="Run scripts/export_attack_taxonomy.py to populate the breadth catalog."
          render={(data) => <FraudLandscape landscape={data} section="taxonomy" />}
        />
      </Card>

      <Card>
        <CardHeader
          title="Generation at scale"
          subtitle="One generation-only benchmark run: no scoring, no fitting, no retraining."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={landscape}
          emptyTitle="No scale benchmark yet"
          emptyBody="Run scripts/run_generation_scale_benchmark.py."
          render={(data) => <FraudLandscape landscape={data} section="scale" />}
        />
      </Card>

      <Card>
        <CardHeader
          title="Fidelity breakdown"
          subtitle="Distributional, behavioral/temporal, and structural components kept separate from constraint validity."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={landscape}
          emptyTitle="No fidelity breakdown yet"
          emptyBody="Run scripts/run_generation_scale_benchmark.py."
          render={(data) => <FraudLandscape landscape={data} section="fidelity" />}
        />
      </Card>

      <Card>
        <CardHeader
          title="Real attacks observed"
          subtitle="Every blueprint the pipeline has actually generated and, where confronted, scored -- pick one to inspect."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={attacksState}
          emptyTitle="No real attacks yet"
          emptyBody="Run scripts/run_bustout_confrontation.py or scripts/run_adaptive_bustout_round.py to populate this list."
          render={(data) => <RealAttackExplorer attacks={data.attacks} />}
        />
      </Card>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">Illustrative reference blueprints</h2>
          <MockDataBadge />
        </div>
        <p className="mb-3 text-xs text-[var(--color-ink-muted)]">
          One canonical, hand-written blueprint per family for orientation -- not fitted to any real
          run. See "Real attacks observed" above for what the pipeline actually produced.
        </p>
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          {ATTACK_FAMILIES.map((f) => (
            <BlueprintPanel key={f.id} blueprint={BASE_BLUEPRINTS[f.id]} />
          ))}
        </div>
      </div>
    </div>
  );
}
