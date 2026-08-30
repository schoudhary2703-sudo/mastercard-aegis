import { useCallback } from "react";
import { fetchAttacks, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { PageHeader } from "../components/ui/PageHeader";
import { FraudLandscape } from "../components/landscape/FraudLandscape";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";

/**
 * Identify (step 1): breadth. This screen answers exactly one judging
 * criterion -- diversity of attacks identified -- and nothing else.
 *
 * "Generation at scale" and "Fidelity breakdown" used to sit here too. They
 * are generation evidence, not identification evidence, so they moved to
 * step 2 where the criterion they answer (fidelity of attacks in simulation)
 * is being argued. The hand-written illustrative blueprints were removed
 * outright: mock parameters on the page that establishes breadth invited
 * exactly the wrong reading of the 14 identified vectors.
 */
export function AttackTaxonomyPage() {
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);
  const landscapeFetch = useCallback((signal: AbortSignal) => fetchLandscape(signal), []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Step 1 · Identify"
        title="The GenAI-enabled payment fraud surface, mapped — and the three families we simulate end to end."
      >
        Breadth is catalogued with evidence; depth is claimed only where a generator, a detector
        result and a blueprint all exist. Every card carries its own status badge, so the catalog can
        never read as "AEGIS simulates all of these".
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
          title="Real attacks observed"
          subtitle="Every blueprint the pipeline has actually generated and, where confronted, scored — pick one to inspect."
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
