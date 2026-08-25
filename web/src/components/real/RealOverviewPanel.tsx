import type { ModelRole, OverviewResponseDTO } from "../../api/types";
import { Card, CardHeader } from "../ui/Card";
import { StatTile } from "../ui/StatTile";
import { HardestEvasionsTable } from "./HardestEvasionsTable";

const ROLE_LABEL: Record<ModelRole, string> = {
  baseline_v1: "Baseline v1",
  defender_v2: "Defender v2 (hardened)",
  defender_v3: "Defender v3 (cross-family hardened)",
};

export function RealOverviewPanel({ overview }: { overview: OverviewResponseDTO }) {
  const current = overview.current_model;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Core defenders trained"
          value={overview.models.length}
          hint={overview.models.map((m) => m.model_version).join(", ") || "None yet"}
        />
        <StatTile label="Confrontations run" value={overview.confrontation_count} />
        <StatTile label="Adaptive rounds run" value={overview.adaptive_round_count} />
        <StatTile
          label="Current model"
          value={current ? current.model_version : "—"}
          tone={current ? "positive" : "neutral"}
          hint={current ? ROLE_LABEL[current.role] : undefined}
        />
      </div>

      {overview.hardest_evasions_preview.length > 0 && (
        <Card>
          <CardHeader
            title="Hardest surviving evasions"
            subtitle="Top 3 by hardness score, across every real confrontation and adaptive round."
          />
          <HardestEvasionsTable evasions={overview.hardest_evasions_preview} />
        </Card>
      )}
    </div>
  );
}
