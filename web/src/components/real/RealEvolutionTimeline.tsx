import type { EvolutionResponseDTO, EvolutionStageDTO, EvolutionStageName } from "../../api/types";
import { Badge } from "../ui/Badge";

const STAGE_SIDE: Record<EvolutionStageName, "attack" | "defend"> = {
  baseline_v1: "defend",
  round_0_attack: "attack",
  adaptive_red: "attack",
  defender_v2_hardening: "defend",
  fresh_confrontation: "attack",
  generation_2_adaptation: "attack",
};

const SIDE_ACCENT: Record<"attack" | "defend", string> = {
  attack: "border-t-[var(--color-attack-600)]",
  defend: "border-t-[var(--color-defend-600)]",
};

function sourceArtifact(stage: EvolutionStageDTO): string | null {
  return (
    stage.model?.source_artifact ??
    stage.confrontation?.source_artifact ??
    stage.adaptive_round?.source_artifact ??
    null
  );
}

function StageCard({ stage, index }: { stage: EvolutionStageDTO; index: number }) {
  const notRun = stage.status === "not_run_yet";
  const side = STAGE_SIDE[stage.stage];
  const artifact = sourceArtifact(stage);

  return (
    <div
      className={`flex min-h-[10rem] flex-col rounded-lg border border-t-2 p-3 ${
        notRun
          ? "border-dashed border-t-[var(--color-border)] border-[var(--color-border)] opacity-60"
          : `${SIDE_ACCENT[side]} border-[var(--color-border)] bg-[var(--color-surface)]`
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-sunken)] text-[10px] font-semibold text-[var(--color-ink-muted)]">
            {index + 1}
          </span>
          <p className="text-xs font-semibold leading-tight text-[var(--color-ink)]">{stage.label}</p>
        </div>
        <Badge variant={notRun ? "neutral" : side === "attack" ? "attack" : "defend"}>
          {notRun ? "Not run" : "Real"}
        </Badge>
      </div>

      <div className="mt-2 flex-1 space-y-1 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        {stage.model && (
          <>
            <p className="font-mono">{stage.model.model_version}</p>
            {stage.model.evaluation_test && (
              <p>
                Test recall {(stage.model.evaluation_test.overall.recall * 100).toFixed(1)}% ·
                precision {(stage.model.evaluation_test.overall.precision * 100).toFixed(1)}%
              </p>
            )}
          </>
        )}

        {stage.confrontation && (
          <>
            <p className="font-mono">{stage.confrontation.report_id}</p>
            <p>
              {stage.confrontation.caught_count}/{stage.confrontation.fraud_count} fraud caught (
              {(stage.confrontation.fraud_recall * 100).toFixed(0)}% recall)
            </p>
          </>
        )}

        {stage.adaptive_round && (
          <>
            <p className="font-mono">{stage.adaptive_round.report_id}</p>
            <p>{stage.adaptive_round.candidate_count} mutated candidate(s) evaluated</p>
            {stage.adaptive_round.after?.fitness != null && (
              <p>Best candidate fitness {stage.adaptive_round.after.fitness.toFixed(3)}</p>
            )}
          </>
        )}

        {stage.hardening && <p>{stage.hardening.hard_positive_count} hard positives promoted</p>}

        {stage.regression && (
          <p>
            F1 vs. {stage.regression.baseline_model_version}:{" "}
            {(stage.regression.metrics.f1?.delta ?? 0) >= 0 ? "+" : ""}
            {((stage.regression.metrics.f1?.delta ?? 0) * 100).toFixed(2)} pts
          </p>
        )}

        {notRun && <p>This stage has not produced an artifact yet.</p>}
      </div>

      {artifact && (
        <p className="mt-2 truncate border-t border-[var(--color-border)] pt-1.5 font-mono text-[10px] text-[var(--color-ink-faint)]">
          {artifact}
        </p>
      )}
    </div>
  );
}

/**
 * The real, closed-loop cycle: Baseline v1 -> Round-0 attack -> Adaptive
 * Red -> Defender v2 hardening -> fresh confrontation -> Generation-2
 * adaptation. Every card and every line of the narrative below it comes
 * straight from `/api/evolution`; nothing here is computed client-side.
 * Attack-side stages carry a red top accent, defend-side stages a green
 * one, so the alternating red/blue loop reads at a glance.
 */
export function RealEvolutionTimeline({ evolution }: { evolution: EvolutionResponseDTO }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {evolution.stages.map((stage, i) => (
          <StageCard key={stage.stage} stage={stage} index={i} />
        ))}
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          What actually happened
        </p>
        <ul className="list-disc space-y-1.5 pl-4 text-sm text-[var(--color-ink)]">
          {evolution.narrative.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
