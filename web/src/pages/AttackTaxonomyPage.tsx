import { BlueprintPanel } from "../components/attack/BlueprintPanel";
import { Card, CardHeader } from "../components/ui/Card";
import { BASE_BLUEPRINTS } from "../mock/blueprints";
import { ATTACK_FAMILIES } from "../types/aegis";

export function AttackTaxonomyPage() {
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

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {ATTACK_FAMILIES.map((f) => (
          <BlueprintPanel key={f.id} blueprint={BASE_BLUEPRINTS[f.id]} />
        ))}
      </div>
    </div>
  );
}
