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
 * Navigation follows the judge story: four primary screens, with the older
 * exploratory pages demoted to a visually quieter secondary group so they
 * stay reachable without competing for attention.
 */
export const PRIMARY_NAV = [
  { to: "/", label: "Mission Control", icon: OverviewIcon, end: true },
  { to: "/attack-lab", label: "Attack Lab", icon: StudioIcon },
  { to: "/co-evolution", label: "Evolution", icon: LoopIcon },
  { to: "/final-benchmark", label: "Final Results", icon: BenchmarkIcon },
];

export const SECONDARY_NAV = [
  { to: "/attack-taxonomy", label: "Taxonomy", icon: TaxonomyIcon },
  { to: "/live-detection", label: "Detections", icon: DetectionIcon },
  { to: "/evaluation", label: "Evaluation", icon: EvaluationIcon },
  { to: "/attack-studio", label: "Studio (demo)", icon: StudioIcon },
];

function linkClasses(isActive: boolean, primary: boolean): string {
  const base = "flex items-center gap-2.5 rounded-lg px-3 transition-standard";
  const size = primary ? "py-2 text-sm font-medium" : "py-1.5 text-xs";
  if (isActive) return `${base} ${size} bg-[var(--color-navy-800)] text-white`;
  return `${base} ${size} text-[var(--color-navy-300)] hover:bg-[var(--color-navy-900)] hover:text-white`;
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <nav className="space-y-0.5 px-3">
        {PRIMARY_NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) => linkClasses(isActive, true)}
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>

      <p className="mt-5 px-6 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-navy-300)]/70">
        More
      </p>
      <nav className="mt-1 space-y-0.5 px-3">
        {SECONDARY_NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) => linkClasses(isActive, false)}
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden h-full w-56 shrink-0 flex-col overflow-y-auto bg-[var(--color-navy-950)] text-[var(--color-navy-300)] lg:flex">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent-500)] text-sm font-bold text-white">
          A
        </div>
        <div>
          <p className="text-sm font-semibold text-white">AEGIS</p>
          <p className="text-[11px] text-[var(--color-navy-300)]">Adversarial Defense</p>
        </div>
      </div>
      <div className="flex-1">
        <SidebarNav />
      </div>
    </aside>
  );
}
