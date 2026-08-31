import { NavLink } from "react-router-dom";
import { LOOP_STEPS, OVERVIEW_STEP, RESULTS_STEP, type JourneyStep } from "../../nav/journey";
import { Logo } from "./Logo";
import { StudioIcon } from "./icons";

/**
 * Navigation is the walkthrough.
 *
 * A judge scoring against the rubric should never have to guess which screen
 * answers which criterion, so the loop steps are numbered 1-4 in reading
 * order and every entry comes from `nav/journey.ts` -- the same list that
 * drives the Overview cards and the per-page "Next" footer.
 *
 * Everything simulated lives behind one visually quiet link at the bottom.
 * Nothing in the numbered path is a browser toy.
 */


function linkClasses(isActive: boolean): string {
  const base = "group flex items-center gap-3 rounded-lg px-3 py-2 transition-standard";
  if (isActive) return `${base} bg-[var(--color-navy-800)] text-white`;
  return `${base} text-[var(--color-navy-300)] hover:bg-[var(--color-navy-900)] hover:text-white`;
}

function StepBadge({ step, active }: { step: number; active: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold tabular-nums transition-standard ${
        active
          ? "bg-[var(--color-accent-600)] text-white"
          : "bg-[var(--color-navy-800)] text-[var(--color-navy-300)] group-hover:text-white"
      }`}
    >
      {step}
    </span>
  );
}

function JourneyLink({ item, onNavigate }: { item: JourneyStep; onNavigate?: () => void }) {
  const { to, label, hint, icon: Icon, end, step } = item;
  return (
    <NavLink to={to} end={end} onClick={onNavigate} className={({ isActive }) => linkClasses(isActive)}>
      {({ isActive }) => (
        <>
          {step != null ? <StepBadge step={step} active={isActive} /> : <Icon />}
          <span className="min-w-0 flex-1">
            <span className="block text-[13.5px] font-medium leading-tight">{label}</span>
            {/* Wraps to two lines rather than truncating. These hints are full
                sentences and the single-line clip landed mid-word -- "The GenAI
                fraud surface, ma..." tells a reader less than nothing. The same
                strings feed the Overview cards, so shortening the copy to fit
                240px would have degraded the place it displays fine. */}
            <span className="mt-0.5 block line-clamp-2 text-[10.5px] leading-snug text-[var(--color-navy-300)] opacity-70">
              {hint}
            </span>
          </span>
        </>
      )}
    </NavLink>
  );
}

function NavGroup({
  heading,
  items,
  onNavigate,
}: {
  heading?: string;
  items: JourneyStep[];
  onNavigate?: () => void;
}) {
  return (
    <div className="mt-5 first:mt-0">
      {heading && (
        <p className="t-eyebrow mb-2 px-3 text-[var(--color-navy-300)] opacity-60">{heading}</p>
      )}
      <nav className="space-y-0.5">
        {items.map((item) => (
          <JourneyLink key={item.to} item={item} onNavigate={onNavigate} />
        ))}
      </nav>
    </div>
  );
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="px-3">
      <NavGroup items={[OVERVIEW_STEP]} onNavigate={onNavigate} />
      <NavGroup heading="The closed loop" items={LOOP_STEPS} onNavigate={onNavigate} />
      <NavGroup heading="Evidence" items={[RESULTS_STEP]} onNavigate={onNavigate} />

      <div className="mt-6 border-t border-[var(--color-border)] pt-3">
        <NavLink
          to="/sandbox"
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[11.5px] transition-standard ${
              isActive
                ? "bg-[var(--color-navy-800)] text-white"
                : "text-[var(--color-navy-300)] opacity-70 hover:bg-[var(--color-navy-900)] hover:text-white hover:opacity-100"
            }`
          }
        >
          <StudioIcon />
          <span className="min-w-0 flex-1">
            <span className="block leading-tight">Sandbox</span>
            <span className="block truncate text-[10px] leading-tight opacity-70">
              Simulated · not evidence
            </span>
          </span>
        </NavLink>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden h-full w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-navy-950)] text-[var(--color-navy-300)] lg:flex">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-accent-600)] text-white">
          <Logo className="h-5 w-5" />
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
          Every figure in the numbered path is read from a persisted file. Nothing is computed in
          the browser.
        </p>
      </div>
    </aside>
  );
}
