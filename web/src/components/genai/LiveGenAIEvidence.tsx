import type { GenAIGuidedGenerationDTO, GenAIResponseDTO, GenAIRunDTO } from "../../api/types";

/**
 * The live GenAI chain, in one compact strip.
 *
 * Reads one row per link so the whole loop is legible at a glance:
 * hypothesis → blind spot → applied mutation → next generation → result.
 *
 * Three honesty rules are enforced here, not left to copy:
 *  - Only `live_*` runs are shown under the LIVE badge. A recorded replay is
 *    never surfaced here; the full panel below shows it as a replay instead.
 *  - `genai_guided` is taken from the server, never re-derived. A record with
 *    incomplete provenance renders its numbers without the guided label.
 *  - Nothing is synthesized. A missing link renders as an explicit dash.
 */

function oneLine(value: string, limit = 180): string {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function num(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function pct(value: number | null | undefined): string {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "—";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] items-baseline gap-2 border-t border-[var(--color-border)] px-3 py-2 first:border-t-0">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {label}
      </span>
      <div className="min-w-0 text-xs leading-snug text-[var(--color-ink)]">{children}</div>
    </div>
  );
}

function Chip({ children, tone = "muted" }: { children: React.ReactNode; tone?: "live" | "muted" }) {
  const style =
    tone === "live"
      ? "bg-[var(--color-risk-low-100)] text-[var(--color-risk-low-600)]"
      : "bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${style}`}>{children}</span>
  );
}

function Mutation({ guided }: { guided: GenAIGuidedGenerationDTO }) {
  const [first, ...rest] = guided.applied_mutations;
  if (!first) return <span className="text-[var(--color-ink-faint)]">—</span>;
  return (
    <span className="font-mono text-[11px]">
      {first.parameter} {num(first.from_value)} → {num(first.to_value)}
      {rest.length > 0 && (
        <span className="ml-1.5 font-sans text-[var(--color-ink-faint)]">
          +{rest.length} more
          {guided.rejected_mutations.length > 0 &&
            ` · ${guided.rejected_mutations.length} rejected`}
        </span>
      )}
      {rest.length === 0 && guided.rejected_mutations.length > 0 && (
        <span className="ml-1.5 font-sans text-[var(--color-ink-faint)]">
          {guided.rejected_mutations.length} rejected
        </span>
      )}
    </span>
  );
}

export function LiveGenAIEvidence({ genai }: { genai: GenAIResponseDTO }) {
  const attack: GenAIRunDTO | null = genai.live_attack_analyst;
  const blind: GenAIRunDTO | null = genai.live_blind_spot_analyst;
  const guided = genai.latest_guided_generation;
  const stamp = blind ?? attack;

  if (!genai.has_live_genai) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)] px-3 py-2.5">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Live GenAI
        </p>
        <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
          No live model call on disk yet — <code>scripts/run_genai_analysis.py</code>
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex flex-wrap items-center gap-1.5 bg-[var(--color-surface-sunken)] px-3 py-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
          Live GenAI
        </span>
        <Chip tone="live">live: true</Chip>
        {stamp && <Chip>{stamp.provider}</Chip>}
        {stamp && <Chip>{stamp.model}</Chip>}
        {stamp && <Chip>{stamp.prompt_version}</Chip>}
        {guided?.genai_guided && <Chip tone="live">guided generation</Chip>}
      </div>

      <Row label="Attack Analyst">
        {attack?.attack_hypothesis ? (
          oneLine(attack.attack_hypothesis)
        ) : (
          <span className="text-[var(--color-ink-faint)]">—</span>
        )}
      </Row>
      <Row label="Blind spot">
        {blind?.blind_spot_hypothesis ? (
          oneLine(blind.blind_spot_hypothesis)
        ) : (
          <span className="text-[var(--color-ink-faint)]">—</span>
        )}
      </Row>
      <Row label="Applied mutation">
        {guided ? <Mutation guided={guided} /> : <span className="text-[var(--color-ink-faint)]">—</span>}
      </Row>
      <Row label="Next generation">
        {guided?.scenario_id ? (
          <span className="break-all font-mono text-[11px]">{guided.scenario_id}</span>
        ) : (
          <span className="text-[var(--color-ink-faint)]">—</span>
        )}
      </Row>
      <Row label="Result">
        {guided && guided.fraud_count != null ? (
          <span className="tabular-nums">
            <span className="font-semibold text-[var(--color-risk-low-600)]">
              {guided.caught_count} caught
            </span>
            {" · "}
            <span className="font-semibold text-[var(--color-risk-high-600)]">
              {guided.escaped_count} escaped
            </span>
            {" · recall "}
            {pct(guided.recall)}
            {" · fidelity "}
            {num(guided.fidelity_score)}
            {guided.detector_model_version && (
              <span className="ml-1.5 font-mono text-[10px] text-[var(--color-ink-faint)]">
                {guided.detector_model_version}
              </span>
            )}
          </span>
        ) : (
          <span className="text-[var(--color-ink-faint)]">—</span>
        )}
      </Row>
      <Row label="Provenance">
        <span className="break-all font-mono text-[10px] text-[var(--color-ink-muted)]">
          {guided?.genai_run_id || stamp?.run_id || "—"}
          {guided?.seed != null && ` · seed ${guided.seed}`}
        </span>
      </Row>
    </div>
  );
}
