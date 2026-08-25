import type { FinalBenchmarkSummaryDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

/**
 * A short, honest read of the benchmark -- every sentence is assembled from
 * real fields on `FinalBenchmarkSummaryDTO` (model_comparison deltas, the
 * LOAFO verdict, the weakest-family flag); nothing here is a fixed string
 * with numbers baked in.
 */
export function BenchmarkInterpretation({ summary }: { summary: FinalBenchmarkSummaryDTO }) {
  const { model_comparison, loafo, claim_flags } = summary;
  const lines: string[] = [];

  const v1 = model_comparison?.baseline_v1;
  const v2 = model_comparison?.defender_v2;
  const v3 = model_comparison?.defender_v3;
  if (v2?.f1 != null && v3?.f1 != null) {
    const deltaVsV2 = (v3.f1 - v2.f1) * 100;
    const vsBaseline =
      v1?.f1 != null ? `, ${v3.f1 >= v1.f1 ? "at or above" : "still below"} baseline v1's ${(v1.f1 * 100).toFixed(1)}%` : "";
    lines.push(
      `Cross-family hardening ${deltaVsV2 >= 0 ? "improved" : "reduced"} native PaySim F1 by ` +
        `${Math.abs(deltaVsV2).toFixed(2)} points versus Defender v2 (${(v2.f1 * 100).toFixed(1)}% -> ` +
        `${(v3.f1 * 100).toFixed(1)}%)${vsBaseline}.`,
    );
  }

  if (loafo) {
    lines.push(
      `Generalization to a completely unseen attack family is ${loafo.overall_verdict}: mean LOAFO ` +
        `recall across all three families is ${(loafo.mean_loafo_recall * 100).toFixed(0)}%.`,
    );
  }

  const weakest = claim_flags.weakest_unseen_family;
  if (typeof weakest === "string" && loafo) {
    const entry = loafo.per_family.find((f) => f.attack_family === weakest);
    const detail = entry
      ? ` (${(entry.loafo_recall * 100).toFixed(0)}% LOAFO recall vs. ${(entry.defender_v3_recall_same_scenario * 100).toFixed(0)}% ` +
        "for Defender v3, which was trained on it)"
      : "";
    lines.push(`${familyLabel(weakest)} remains the weakest unseen-family case${detail}.`);
  }

  if (lines.length === 0) {
    lines.push("Not enough real benchmark data has been produced yet to interpret.");
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        Interpretation
      </p>
      <ul className="list-disc space-y-1.5 pl-4 text-sm text-[var(--color-ink)]">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {claim_flags.universal_fraud_detection === false && (
        <p className="mt-3 text-xs font-medium text-[var(--color-risk-high-600)]">
          Not a claim of universal fraud detection.
        </p>
      )}
    </div>
  );
}
