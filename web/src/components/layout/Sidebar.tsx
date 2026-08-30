import { NavLink } from "react-router-dom";
import {
  BenchmarkIcon,
  DetectionIcon,
  EvaluationIcon,
  LoopIcon,
  OverviewIcon,
  StudioIcon,
  TaxonomyIcon,
} from "./icons";

/**
 * Navigation mirrors the challenge's own three pillars -- identify, generate,
 * defend -- then the evidence that backs them. A judge scoring against the
 * rubric can find the screen for each criterion without a map.
 */
export const PRIMARY_NAV = [
  { to: "/", label: "Mission Control", icon: OverviewIcon, end: true },
];

export const LOOP_NAV = [
  { to: "/attack-taxonomy", label: "Identify", icon: TaxonomyIcon, hint: "Attack atlas" },
  { to: "/attack-lab", label: "Generate", icon: StudioIcon, hint: "Campaign replay" },
  { to: "/live-detection", label: "Defend", icon: DetectionIcon, hint: "Live scoring" },
  { to: "/co-evolution", label: "Evolve", icon: LoopIcon, hint: "Hardening rounds" },
];

export const EVIDENCE_NAV = [
  { to: "/final-benchmark", label: "Final Results", icon: BenchmarkIcon, hint: "v1 → v3, LOAFO" },
  { to: "/evaluation", label: "Evaluation", icon: EvaluationIcon, hint: "Per-model metrics" },
  { to: "/attack-studio", label: "Studio", icon: StudioIcon, hint: "Simulated demo" },
];

function linkClasses(isActive: boolean): string {
  const base =
    "group flex items-center gap-3 rounded-lg px-3 py-2 transition-standard";
  if (isActive) {
    return `${base} bg-[var(--color-navy-800)] text-white`;
  }
  return `${base} text-[var(--color-navy-300)] hover:bg-[var(--color-navy-900)] hover:text-white`;
}

function NavGroup({
  heading,
  items,
  onNavigate,
}: {
  heading?: string;
  items: { to: string; label: string; icon: () => React.ReactElement; hint?: string; end?: boolean }[];
  onNavigate?: () => void;
}) {
  return (
    <div className="mt-5 first:mt-0">
      {heading && (
        <p className="t-eyebrow mb-2 px-3 text-[var(--color-navy-300)] opacity-60">{heading}</p>
      )}
      <nav className="space-y-0.5">
        {items.map(({ to, label, icon: Icon, hint, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) => linkClasses(isActive)}
          >
            <Icon />
            <span className="min-w-0 flex-1">
              <span className="block text-[13.5px] font-medium leading-tight">{label}</span>
              {hint && (
                <span className="block truncate text-[10.5px] leading-tight text-[var(--color-navy-300)] opacity-70">
                  {hint}
                </span>
              )}
            </span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="px-3">
      <NavGroup items={PRIMARY_NAV} onNavigate={onNavigate} />
      <NavGroup heading="The loop" items={LOOP_NAV} onNavigate={onNavigate} />
      <NavGroup heading="Evidence" items={EVIDENCE_NAV} onNavigate={onNavigate} />
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden h-full w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-navy-950)] text-[var(--color-navy-300)] lg:flex">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-accent-600)] text-sm font-semibold text-white">
          A
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-wide text-white">AEGIS</p>
          <p className="t-eyebrow text-[var(--color-navy-300)]">Defense console</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pb-4">
        <SidebarNav />
      </div>

      <div className="border-t border-[var(--color-border)] px-5 py-4">
        <p className="flex items-center gap-2 text-[11.5px] font-medium text-[var(--color-defend-500)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-defend-500)]" />
          Live pipeline artifacts
        </p>
        <p className="mt-1.5 text-[10.5px] leading-relaxed text-[var(--color-navy-300)] opacity-80">
          Every figure is read from a persisted file. Nothing is computed in the browser.
        </p>
      </div>
    </aside>
  );
}
