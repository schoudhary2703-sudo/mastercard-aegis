import type { GenAIResponseDTO, GenAIRunDTO } from "../../api/types";
import { Details } from "../ui/Details";

/**
 * Compact view of the two GenAI reasoning stages.
 *
 * Two honesty rules are enforced here rather than left to copy:
 *  - When no run artifact exists, the panel says the layer has not been run.
 *    It never renders illustrative reasoning.
 *  - `live` is surfaced as a distinct chip, so a recorded/offline replay is
 *    visibly a replay in the same place a live call would be.
 */

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function strList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function ProvenanceChips({ run }: { run: GenAIRunDTO }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
      <span
        className={`rounded-full px-2 py-0.5 font-bold uppercase tracking-wide ${
          run.live
            ? "bg-[var(--color-risk-low-100)] text-[var(--color-risk-low-600)]"
            : "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]"
        }`}
      >
        {run.live ? "Live" : "Recorded"}
      </span>
      <span className="rounded-full bg-[var(--color-surface-sunken)] px-2 py-0.5 font-medium text-[var(--color-ink-muted)]">
        {run.provider}
      </span>
      <span className="rounded-full bg-[var(--color-surface-sunken)] px-2 py-0.5 font-mono text-[var(--color-ink-muted)]">
        {run.model}
      </span>
      <span className="rounded-full bg-[var(--color-surface-sunken)] px-2 py-0.5 font-mono text-[var(--color-ink-faint)]">
        {run.prompt_version}
      </span>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {label}
      </p>
      <div className="mt-0.5 text-xs leading-snug text-[var(--color-ink)]">{children}</div>
    </div>
  );
}

function Chips({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <span
          key={item}
          className="rounded bg-[var(--color-surface-sunken)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-muted)]"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function Confidence({ value }: { value: unknown }) {
  if (typeof value !== "number") return null;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--color-border)]">
        <div
          className="h-full rounded-full bg-[var(--color-accent-500)]"
          style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
        />
      </div>
      <span className="text-xs font-semibold tabular-nums text-[var(--color-ink)]">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

function NotRunCard({ title, what }: { title: string; what: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)] p-4">
      <p className="text-xs font-semibold text-[var(--color-ink)]">{title}</p>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">Not run yet — no artifact on disk.</p>
      <p className="mt-2 text-[11px] text-[var(--color-ink-faint)]">Would produce: {what}</p>
      <code className="mt-2 block overflow-x-auto rounded bg-[var(--color-surface)] px-2 py-1 font-mono text-[10px] text-[var(--color-ink-muted)]">
        scripts/run_genai_analysis.py
      </code>
    </div>
  );
}

function AttackAnalystCard({ run }: { run: GenAIRunDTO }) {
  const r = run.response ?? {};
  const params = Array.isArray(r.recommended_simulator_parameters)
    ? (r.recommended_simulator_parameters as Record<string, unknown>[])
    : [];

  return (
    <div className="space-y-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-attack-600)]">Attack Analyst</p>
        <ProvenanceChips run={run} />
      </div>
      {str(r.attack_hypothesis) && <Field label="Hypothesis">{str(r.attack_hypothesis)}</Field>}
      {str(r.genai_enablement) && (
        <Field label="GenAI enablement">{str(r.genai_enablement)}</Field>
      )}
      {strList(r.observable_signals).length > 0 && (
        <Field label="Observable signals">
          <Chips items={strList(r.observable_signals)} />
        </Field>
      )}
      {params.length > 0 && (
        <Field label="Recommended parameters">
          <Chips
            items={params
              .map((p) => `${String(p.name)} = ${String(p.value)}`)
              .filter((s) => !s.startsWith("undefined"))}
          />
        </Field>
      )}
      <Field label="Confidence">
        <Confidence value={r.confidence} />
      </Field>
    </div>
  );
}

function BlindSpotCard({ run }: { run: GenAIRunDTO }) {
  const r = run.response ?? {};
  const proposals = Array.isArray(r.mutation_proposals)
    ? (r.mutation_proposals as Record<string, unknown>[])
    : [];

  return (
    <div className="space-y-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-attack-600)]">Blind-Spot Analyst</p>
        <ProvenanceChips run={run} />
      </div>
      {str(r.blind_spot_hypothesis) && (
        <Field label="Detected blind spot">{str(r.blind_spot_hypothesis)}</Field>
      )}
      {strList(r.evidence).length > 0 && (
        <Field label="Evidence">
          <ul className="list-disc space-y-0.5 pl-4">
            {strList(r.evidence).map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Field>
      )}
      {proposals.length > 0 && (
        <Field label="Bounded mutation">
          <Chips
            items={proposals.map(
              (p) =>
                `${String(p.parameter)} ${String(p.direction)}${
                  typeof p.magnitude === "number" ? ` ±${p.magnitude}` : ""
                }`,
            )}
          />
        </Field>
      )}
      {strList(r.expected_trade_offs).length > 0 && (
        <Field label="Expected trade-off">{strList(r.expected_trade_offs).join(" · ")}</Field>
      )}
      <Field label="Confidence">
        <Confidence value={r.confidence} />
      </Field>
    </div>
  );
}

export function GenAIAnalystPanel({ genai }: { genai: GenAIResponseDTO }) {
  const attack = genai.attack_analyst;
  const blind = genai.blind_spot_analyst;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-2">
        {attack ? (
          <AttackAnalystCard run={attack} />
        ) : (
          <NotRunCard
            title="Attack Analyst"
            what="attack hypothesis, GenAI enablement, observable signals, simulator parameters, confidence"
          />
        )}
        {blind ? (
          <BlindSpotCard run={blind} />
        ) : (
          <NotRunCard
            title="Blind-Spot Analyst"
            what="detected blind spot, evidence, bounded mutation proposal, trade-offs, confidence"
          />
        )}
      </div>

      <Details summary="How GenAI is bounded here">
        GenAI reasons at two points only: it turns fraud research into structured simulator
        parameters, and turns real detector failures into bounded mutation proposals. It never
        emits transaction rows, fits a model, or produces a reported number — deterministic seeded
        simulators and XGBoost do that, which is what keeps every corpus reproducible from its
        seed. Mutation magnitudes are capped and proposals touching non-mutable parameters are
        rejected, not clamped. See <code>docs/GENAI_LAYER.md</code>.
      </Details>
    </div>
  );
}
