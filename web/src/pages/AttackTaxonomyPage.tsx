import { useCallback } from "react";
import { fetchAttacks, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { FraudLandscape } from "../components/landscape/FraudLandscape";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";

export function AttackTaxonomyPage() {
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);
  const landscapeFetch = useCallback((signal: AbortSignal) => fetchLandscape(signal), []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-6">
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

    </div>
  );
}
