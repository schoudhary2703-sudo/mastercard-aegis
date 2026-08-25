import { useCallback, useMemo, useState } from "react";
import { fetchAttack } from "../../api/client";
import type { AttackSummaryDTO } from "../../api/types";
import { useApiResource } from "../../api/useApiResource";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";
import { ApiStateSection } from "./ApiStateSection";
import { RealAttackDetailPanel } from "./RealAttackDetailPanel";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

/**
 * A picker over real attack blueprints (grouped by family) plus the detail
 * panel for whichever one is selected. Takes an already-fetched list so the
 * caller controls the top-level loading/error/empty states; this component
 * only owns the selection and the per-attack detail fetch.
 */
export function RealAttackExplorer({ attacks }: { attacks: AttackSummaryDTO[] }) {
  const [selectedId, setSelectedId] = useState<string>(attacks[0]?.attack_id ?? "");

  const detailFetch = useCallback(
    (signal: AbortSignal) => fetchAttack(selectedId, signal),
    [selectedId],
  );
  const detailState = useApiResource(detailFetch, [selectedId]);

  const byFamily = useMemo(() => {
    const groups = new Map<string, AttackSummaryDTO[]>();
    for (const a of attacks) {
      const list = groups.get(a.attack_family) ?? [];
      list.push(a);
      groups.set(a.attack_family, list);
    }
    return groups;
  }, [attacks]);

  if (attacks.length === 0) {
    return <p className="text-sm text-[var(--color-ink-faint)]">No real attacks recorded yet.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {[...byFamily.entries()].map(([family, list]) => (
          <div key={family}>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
              {familyLabel(family)} ({list.length})
            </p>
            <div className="flex flex-wrap gap-1.5">
              {list.map((a) => (
                <button
                  key={a.attack_id}
                  type="button"
                  onClick={() => setSelectedId(a.attack_id)}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-xs transition-standard ${
                    a.attack_id === selectedId
                      ? "border-[var(--color-accent-600)] bg-[var(--color-accent-600)]/10 text-[var(--color-accent-600)]"
                      : "border-[var(--color-border)] text-[var(--color-ink-muted)] hover:border-[var(--color-border-strong)]"
                  }`}
                >
                  {a.attack_id} · gen {a.generation}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-[var(--color-border)] pt-4">
        <ApiStateSection
          state={detailState}
          emptyTitle="No detail available"
          emptyBody="This blueprint has no further detail on disk."
          render={(detail) => <RealAttackDetailPanel attack={detail} />}
        />
      </div>
    </div>
  );
}
