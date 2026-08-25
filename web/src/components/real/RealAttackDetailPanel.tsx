import type { AttackDetailDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";
import { Badge } from "../ui/Badge";
import { HardestEvasionsTable } from "./HardestEvasionsTable";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

function readString(obj: Record<string, unknown>, key: string): string | null {
  const v = obj[key];
  return typeof v === "string" ? v : null;
}

function readNumber(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}

/**
 * Everything real known about one attack blueprint: its own fields plus,
 * for each real confrontation it appeared in, that confrontation's status
 * and the hardest evasions it produced (with per-transaction fidelity).
 * Every value here is read straight off `AttackDetailDTO` -- nothing is
 * recomputed or explained beyond what the backend already states.
 */
export function RealAttackDetailPanel({ attack }: { attack: AttackDetailDTO }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="attack">{familyLabel(attack.attack_family)}</Badge>
        <Badge variant="neutral">Generation {attack.generation}</Badge>
        {attack.parent_blueprint_id && (
          <Badge variant="neutral">parent: {attack.parent_blueprint_id}</Badge>
        )}
        <span className="font-mono text-xs text-[var(--color-ink-faint)]">{attack.attack_id}</span>
      </div>

      {attack.description && (
        <p className="text-sm text-[var(--color-ink-muted)]">{attack.description}</p>
      )}
      {attack.objective && (
        <p className="text-xs text-[var(--color-ink-faint)]">Objective: {attack.objective}</p>
      )}

      {attack.target_features.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Target features
          </p>
          <div className="flex flex-wrap gap-1.5">
            {attack.target_features.map((f) => (
              <Badge key={f} variant="neutral">
                {f}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {attack.sequence.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Behavioral sequence
          </p>
          <ol className="space-y-1.5">
            {attack.sequence.map((step, i) => {
              const description = readString(step, "description") ?? readString(step, "action") ?? "step";
              const order = readNumber(step, "order") ?? i;
              return (
                <li key={`${order}-${description}`} className="flex gap-3 text-sm">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-sunken)] text-[11px] font-semibold text-[var(--color-ink-muted)]">
                    {order + 1}
                  </span>
                  <span className="text-[var(--color-ink-muted)]">{description}</span>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Confrontation status
        </p>
        {attack.confrontation_results.length === 0 ? (
          <p className="text-sm text-[var(--color-ink-faint)]">
            Not yet confronted against a detector.
          </p>
        ) : (
          <div className="space-y-3">
            {attack.confrontation_results.map((c) => (
              <div key={c.report_id} className="rounded-lg border border-[var(--color-border)] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-xs text-[var(--color-ink)]">{c.report_id}</span>
                  <div className="flex gap-2">
                    {c.adaptive && <Badge variant="neutral">adaptive</Badge>}
                    <Badge variant="defend">{c.model_version}</Badge>
                  </div>
                </div>
                <p className="mt-1.5 text-xs text-[var(--color-ink-muted)]">
                  {c.caught_count}/{c.fraud_count} fraud caught ({(c.fraud_recall * 100).toFixed(0)}%
                  recall) · {c.total_transactions} transactions scored
                </p>
                {c.hardest_evasions.length > 0 && (
                  <div className="mt-2">
                    <HardestEvasionsTable evasions={c.hardest_evasions} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
