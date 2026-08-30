import { Badge } from "../ui/Badge";
import { ProvenanceChip } from "../ui/ProvenanceChip";

/**
 * Marks a section as backed by real, persisted AEGIS pipeline artifacts.
 * Thin wrapper over `ProvenanceChip` so every "real data" marker in the app
 * upgrades in one place; pass `source` to name the artifact.
 */
export function RealDataBadge({ source }: { source?: string } = {}) {
  return <ProvenanceChip source={source} />;
}

/** Marks a section as the client-side, deterministic mock demo. */
export function MockDataBadge() {
  return <Badge variant="neutral">Simulated demo (not real data)</Badge>;
}
