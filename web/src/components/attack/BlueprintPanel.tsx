import { Badge } from "../ui/Badge";
import { Card, CardHeader } from "../ui/Card";
import type { AttackBlueprint } from "../../types/aegis";

export function BlueprintPanel({ blueprint }: { blueprint: AttackBlueprint }) {
  return (
    <Card>
      <CardHeader
        title={blueprint.attack_id}
        subtitle={blueprint.objective}
        action={<Badge variant="attack">Generation {blueprint.generation}</Badge>}
      />
      <p className="text-sm text-[var(--color-ink-muted)]">{blueprint.description}</p>

      <div className="mt-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Behavioral sequence
        </p>
        <ol className="space-y-1.5">
          {blueprint.sequence.map((step) => (
            <li key={step.order} className="flex gap-3 text-sm">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-sunken)] text-[11px] font-semibold text-[var(--color-ink-muted)]">
                {step.order + 1}
              </span>
              <span className="text-[var(--color-ink-muted)]">{step.description}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Parameters
        </p>
        <div className="grid grid-cols-2 gap-2">
          {Object.values(blueprint.parameters).map((p) => (
            <div key={p.name} className="rounded-lg border border-[var(--color-border)] px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--color-ink)]">{p.name}</span>
                {!p.mutable && <Badge variant="neutral">fixed</Badge>}
              </div>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--color-ink-muted)]">
                {String(p.value)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
