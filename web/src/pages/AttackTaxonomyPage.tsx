import { useCallback } from "react";
import { fetchAttacks, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { FraudLandscape } from "../components/landscape/FraudLandscape";
import { Card } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";

/**
 * Identify (step 1): breadth. This screen argues exactly one judging
 * criterion -- diversity of attacks identified -- and nothing else.
 *
 * "Generation at scale" and "Fidelity breakdown" used to sit here too, which
 * made this the longest page in the console at nearly four screens while
 * arguing a criterion it does not own. Both are generation evidence and moved
 * to step 2, where fidelity is the point.
 */
export function AttackTaxonomyPage() {
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);
  const landscapeFetch = useCallback((signal: AbortSignal) => fetchLandscape(signal), []);
  const landscape = useApiResource(landscapeFetch, []);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="t-h1 text-[var(--color-ink)]">
          The GenAI-enabled payment fraud surface, mapped.
        </h1>
        <p className="t-body mt-2 max-w-2xl text-[var(--color-ink-muted)]">
          Breadth is catalogued with evidence. Depth is claimed only where a generator, a blueprint
          and a real detector result all exist &mdash; three of fourteen.
        </p>
      </header>

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="t-eyebrow text-[var(--color-ink-faint)]">Fraud landscape</h2>
          <RealDataBadge />
        </div>
        <Card>
          <ApiStateSection
            state={landscape}
            emptyTitle="No taxonomy artifact yet"
            emptyBody="Run scripts/export_attack_taxonomy.py to populate the breadth catalog."
            render={(data) => <FraudLandscape landscape={data} section="taxonomy" />}
          />
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="t-eyebrow text-[var(--color-ink-faint)]">Real attacks observed</h2>
          <RealDataBadge />
        </div>
        <p className="t-body-sm mb-3 text-[var(--color-ink-muted)]">
          Every blueprint the pipeline has actually generated and, where confronted, scored.
        </p>
        <Card>
          <ApiStateSection
            state={attacksState}
            emptyTitle="No real attacks yet"
            emptyBody="Run scripts/run_bustout_confrontation.py or scripts/run_adaptive_bustout_round.py to populate this list."
            render={(data) => <RealAttackExplorer attacks={data.attacks} />}
          />
        </Card>
      </section>
    </div>
  );
}
