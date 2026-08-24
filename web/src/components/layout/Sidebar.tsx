import { NavLink } from "react-router-dom";
import {
  DetectionIcon,
  EvaluationIcon,
  LoopIcon,
  OverviewIcon,
  StudioIcon,
  TaxonomyIcon,
} from "./icons";

const NAV = [
  { to: "/", label: "Overview", icon: OverviewIcon, end: true },
  { to: "/attack-studio", label: "Attack Studio", icon: StudioIcon },
  { to: "/live-detection", label: "Live Detection", icon: DetectionIcon },
  { to: "/co-evolution", label: "Co-Evolution", icon: LoopIcon },
  { to: "/attack-taxonomy", label: "Attack Taxonomy", icon: TaxonomyIcon },
  { to: "/evaluation", label: "Evaluation", icon: EvaluationIcon },
];

export function Sidebar() {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col bg-[var(--color-navy-950)] text-[var(--color-navy-300)]">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent-500)] text-sm font-bold text-white">
          A
        </div>
        <div>
          <p className="text-sm font-semibold text-white">AEGIS</p>
          <p className="text-[11px] text-[var(--color-navy-300)]">Adversarial Defense</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-standard ${
                isActive
                  ? "bg-[var(--color-navy-800)] text-white"
                  : "text-[var(--color-navy-300)] hover:bg-[var(--color-navy-900)] hover:text-white"
              }`
            }
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-[var(--color-navy-800)] px-5 py-4 text-[11px] text-[var(--color-navy-300)]">
        <p className="font-medium text-white/80">Mock demo mode</p>
        <p className="mt-0.5">All data is locally generated. No backend calls.</p>
      </div>
    </aside>
  );
}
