import { useCallback } from "react";
import { fetchAttacks } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { BlueprintPanel } from "../components/attack/BlueprintPanel";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { MockDataBadge, RealDataBadge } from "../components/real/RealBadge";
import { RealAttackExplorer } from "../components/real/RealAttackExplorer";
import { BASE_BLUEPRINTS } from "../mock/blueprints";
import { ATTACK_FAMILIES } from "../types/aegis";

export function AttackTaxonomyPage() {
  const attacksFetch = useCallback((signal: AbortSignal) => fetchAttacks(signal), []);
  const attacksState = useApiResource(attacksFetch, [], (data) => data.attacks.length === 0);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Three families, deliberately"
          subtitle="The taxonomy is fixed by design -- no fourth family is added, ever."
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {ATTACK_FAMILIES.map((f) => (
            <div key={f.id} className="rounded-lg border border-[var(--color-border)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--color-ink)]">{f.label}</p>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{f.blurb}</p>
            </div>
          ))}
        </div>
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
