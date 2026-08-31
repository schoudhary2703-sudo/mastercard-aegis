import type { ReactElement } from "react";
import {
  BenchmarkIcon,
  DetectionIcon,
  LoopIcon,
  OverviewIcon,
  StudioIcon,
  TaxonomyIcon,
} from "../components/layout/icons";

/**
 * The judge journey -- one ordered list, one source of truth.
 *
 * The challenge scores five things: diversity of attacks identified, fidelity
 * of attacks in simulation, detection efficacy, novelty, and real-world
 * feasibility. Rather than leave a judge to infer which screen answers which
 * criterion, the nav *is* the loop, numbered, and each step declares the
 * criterion it is evidence for.
 *
 * Sidebar, the Overview judge-path cards and the per-page "Next" footer all
 * read from this array, so the walkthrough can never disagree with itself.
 */

export interface JourneyStep {
  /** Loop position. `null` for the framing screen and the closing evidence. */
  step: number | null;
  to: string;
  label: string;
  /** One line, shown under the nav label and on the Overview cards. */
  hint: string;
  /** The judging criterion this screen is the evidence for. */
  rubric: string;
  icon: () => ReactElement;
  end?: boolean;
}

export const OVERVIEW_STEP: JourneyStep = {
  step: null,
  to: "/",
  label: "Overview",
  hint: "What AEGIS is, in one figure",
  rubric: "Novelty · real-world feasibility",
  icon: OverviewIcon,
  end: true,
};

export const LOOP_STEPS: JourneyStep[] = [
  {
    step: 1,
    to: "/attack-taxonomy",
    label: "Identify",
    hint: "The GenAI fraud surface, mapped",
    rubric: "Diversity of attacks identified",
    icon: TaxonomyIcon,
  },
  {
    step: 2,
    to: "/attack-lab",
    label: "Generate",
    hint: "Blueprints, simulation, fidelity",
    rubric: "Fidelity of attacks in simulation",
    icon: StudioIcon,
  },
  {
    step: 3,
    to: "/live-detection",
    label: "Defend",
    hint: "Every transaction the detector scored",
    rubric: "Detection efficacy",
    icon: DetectionIcon,
  },
  {
    step: 4,
    to: "/co-evolution",
    label: "Evolve",
    hint: "What escaped, and what closed it",
    rubric: "Novelty of the closed loop",
    icon: LoopIcon,
  },
];

export const RESULTS_STEP: JourneyStep = {
  step: null,
  to: "/final-benchmark",
  label: "Results",
  hint: "v1 → v3, operating point, LOAFO",
  rubric: "Detection efficacy · generalization",
  icon: BenchmarkIcon,
};

/** The full walkthrough, in the order a judge should read it. */
export const JOURNEY: JourneyStep[] = [OVERVIEW_STEP, ...LOOP_STEPS, RESULTS_STEP];

/** The step currently being viewed, matched on pathname. */
export function stepFor(pathname: string): JourneyStep | null {
  const path = pathname === "" ? "/" : pathname;
  if (path === "/") return OVERVIEW_STEP;
  return JOURNEY.find((s) => s.to !== "/" && path.startsWith(s.to)) ?? null;
}

/** The screen that follows `pathname` in the walkthrough, if any. */
export function nextStepFor(pathname: string): JourneyStep | null {
  const current = stepFor(pathname);
  if (!current) return null;
  const index = JOURNEY.indexOf(current);
  return index >= 0 && index < JOURNEY.length - 1 ? JOURNEY[index + 1] : null;
}
