import type { CSSProperties } from "react";

/** Shared Recharts styling so tooltips/axes read correctly on the dark console. */

export const CHART_TOOLTIP_STYLE: CSSProperties = {
  borderRadius: 8,
  border: "1px solid var(--color-border-strong)",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
  fontSize: 12,
  boxShadow: "var(--shadow-elevated)",
};

export const CHART_TOOLTIP_ITEM_STYLE: CSSProperties = {
  color: "var(--color-ink-muted)",
};

export const CHART_TOOLTIP_LABEL_STYLE: CSSProperties = {
  color: "var(--color-ink)",
  fontWeight: 600,
};
