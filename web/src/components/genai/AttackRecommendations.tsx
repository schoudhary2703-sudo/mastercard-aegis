import type { AttackRecommendationPreviewDTO, RecommendedParameterDTO } from "../../api/types";

/**
 * What the live Attack Analyst recommended vs what the blueprint would accept.
 *
 * Display-only by construction: the server's preview adapter applies nothing
 * (`applied` is always false), so this panel says "recommended", never
 * "applied". The rejected rows are the point — they show the blueprint's
 * declared bounds refusing an out-of-range value rather than clamping it.
 */

function show(value: string | number | boolean | null): string {
  if (value === null) return "—";
  return typeof value === "number" ? String(value) : String(value);
}

function Row({ parameter }: { parameter: RecommendedParameterDTO }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 border-t border-[var(--color-border)] px-3 py-1.5 first:border-t-0">
      <span className="font-mono text-[11px] text-[var(--color-ink)]">{parameter.name}</span>
      <span className="flex items-baseline gap-1.5">
        <span className="font-mono text-[11px] tabular-nums text-[var(--color-ink-muted)]">
          {show(parameter.current_value)} → {show(parameter.recommended_value)}
        </span>
        {parameter.actionable ? (
          <span className="rounded-full bg-[var(--color-risk-low-100)] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[var(--color-risk-low-600)]">
            In bounds
          </span>
        ) : (
          <span className="rounded-full bg-[var(--color-risk-high-100)] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[var(--color-risk-high-600)]">
            Rejected
          </span>
        )}
      </span>
      {!parameter.actionable && parameter.reason && (
        <span className="w-full text-[10px] text-[var(--color-ink-faint)]">{parameter.reason}</span>
      )}
    </div>
  );
}

export function AttackRecommendations({
  preview,
}: {
  preview: AttackRecommendationPreviewDTO;
}) {
  if (preview.recommended_count === 0) return null;
  const rejected = preview.recommended_count - preview.actionable_count;

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--color-surface-sunken)] px-3 py-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
          Recommended vs actionable
        </span>
        <span className="text-[10px] text-[var(--color-ink-muted)]">
          <span className="font-semibold text-[var(--color-ink)]">
            {preview.actionable_count}/{preview.recommended_count}
          </span>{" "}
          in bounds
          {rejected > 0 && ` · ${rejected} out of range`} · not applied
        </span>
      </div>
      <div>
        {preview.parameters.map((parameter) => (
          <Row key={parameter.name} parameter={parameter} />
        ))}
      </div>
      <p className="border-t border-[var(--color-border)] px-3 py-1.5 text-[10px] text-[var(--color-ink-faint)]">
        Checked against <code className="font-mono">{preview.blueprint_id}</code>&rsquo;s declared
        parameter specs. Surfaced only — applying these would author a new blueprint, which is a
        separate deliberate step.
      </p>
    </div>
  );
}
