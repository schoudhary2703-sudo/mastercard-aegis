import { Badge } from "../ui/Badge";

/** Marks a section as backed by real, persisted AEGIS pipeline artifacts. */
export function RealDataBadge() {
  return <Badge variant="defend">Real pipeline data</Badge>;
}

/** Marks a section as the client-side, deterministic mock demo. */
export function MockDataBadge() {
  return <Badge variant="neutral">Simulated demo (not real data)</Badge>;
}
