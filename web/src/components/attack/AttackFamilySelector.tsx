import { ATTACK_FAMILIES } from "../../types/aegis";
import type { AttackFamily } from "../../types/aegis";

export function AttackFamilySelector({
  value,
  onChange,
}: {
  value: AttackFamily;
  onChange: (family: AttackFamily) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {ATTACK_FAMILIES.map((f) => {
        const active = f.id === value;
        return (
          <button
            key={f.id}
            type="button"
            onClick={() => onChange(f.id)}
            className={`rounded-xl border p-4 text-left transition-standard ${
              active
                ? "border-[var(--color-attack-600)] bg-[var(--color-attack-100)]"
                : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-strong)]"
            }`}
          >
            <p className={`text-sm font-semibold ${active ? "text-[var(--color-attack-600)]" : "text-[var(--color-ink)]"}`}>
              {f.label}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-ink-muted)]">{f.blurb}</p>
          </button>
        );
      })}
    </div>
  );
}
