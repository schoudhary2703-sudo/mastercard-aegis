import { useEffect, useState } from "react";

/**
 * The closed loop as a ring, with a signal travelling it.
 *
 * Six stages clockwise from Identify. Colour carries team attribution (red
 * team invents and mutates, blue team scores and retrains, evaluate is
 * neutral), and the two dashed rings mark the only points where a language
 * model reasons -- the claim the whole submission rests on, made visible
 * rather than asserted in prose.
 *
 * The travelling dot is the one piece of motion in the console. It is not
 * decoration: it changes colour at the halfway point, red while an attack is
 * in flight and green once the escape has become hardening data, which is the
 * loop's actual thesis in one gesture. It is suppressed entirely under
 * `prefers-reduced-motion`.
 *
 * Every figure in the centre panel arrives as a prop. The design this was
 * drawn from hardcoded v1/v2/v3 metrics; hardcoding them here would break the
 * rule the rest of the console keeps -- no number is written into the page,
 * all of them are read from a persisted artifact -- and would go stale the
 * moment the artifacts changed. With no generations supplied the panel simply
 * omits the metrics rather than inventing them.
 */

export type NodeLoopStage =
  | "identify"
  | "generate"
  | "defend"
  | "evaluate"
  | "evolve"
  | "retrain";

export interface LoopGeneration {
  label: string;
  precision: string;
  recall: string;
  fpr: string;
}

interface NodeProps {
  active?: NodeLoopStage;
  generations?: LoopGeneration[];
}

/** Geometry, kept as data so the ring and its labels cannot drift apart. */
const NODES: {
  id: NodeLoopStage;
  n: number;
  cx: number;
  cy: number;
  team: "red" | "blue" | "neutral";
  title: string;
  sub?: string[];
  anchor: "middle" | "start" | "end";
  tx: number;
  ty: number;
  /** Stack sub-lines above the title. Needed where the label sits above
   *  its node -- otherwise the sub-line runs into the circle. */
  subAbove?: boolean;
  genai?: boolean;
}[] = [
  { id: "identify", n: 1, cx: 240, cy: 82, team: "red", title: "Identify", sub: ["attack blueprint"], anchor: "middle", tx: 240, ty: 50, subAbove: true, genai: true },
  { id: "generate", n: 2, cx: 347.38, cy: 134, team: "red", title: "Generate", sub: ["synthetic", "campaign"], anchor: "start", tx: 378.38, ty: 124 },
  { id: "defend", n: 3, cx: 347.38, cy: 238, team: "blue", title: "Defend", sub: ["risk scores"], anchor: "start", tx: 378.38, ty: 235.5 },
  { id: "evaluate", n: 4, cx: 240, cy: 290, team: "neutral", title: "Evaluate", sub: ["caught / escaped"], anchor: "middle", tx: 240, ty: 330 },
  { id: "evolve", n: 5, cx: 132.62, cy: 238, team: "red", title: "Evolve", sub: ["bounded", "mutation"], anchor: "end", tx: 101.62, ty: 228, genai: true },
  { id: "retrain", n: 6, cx: 132.62, cy: 134, team: "blue", title: "Retrain", sub: ["next-gen", "detector"], anchor: "end", tx: 101.62, ty: 124 },
];

const EDGES = [
  "M272.09 85.55Q305.72 90.53 327.68 112.46",
  "M359.77 159.08Q371.44 186 359.77 212.92",
  "M327.68 259.54Q305.72 281.47 272.09 286.45",
  "M207.91 286.45Q174.28 281.47 152.32 259.54",
  "M120.23 212.92Q108.56 186 120.23 159.08",
];
/** The closing edge, drawn distinctly: retrain feeding back into identify. */
const CLOSING_EDGE = "M152.32 112.46Q174.28 90.53 207.91 85.55";

const TEAM_FILL: Record<"red" | "blue" | "neutral", string> = {
  red: "var(--color-attack-600)",
  blue: "var(--color-defend-600)",
  neutral: "var(--color-surface)",
};

export function NodeLoop({ active, generations }: NodeProps) {
  const list = generations ?? [];
  const [gen, setGen] = useState(0);

  // The centre panel walks the defender generations in time with the signal's
  // lap, so the ring shows v1 hardening into v3 as the loop turns.
  //
  // Driven by a timer rather than the dot's `animationiteration` event: the
  // offset-path animation runs on the compositor and does not reliably emit
  // iteration events, so an event-driven cycle silently froze on one
  // generation. The interval matches the 7s lap in index.css -- if you change
  // one, change the other.
  //
  // Frozen on the newest generation when a stage is explicitly active (the
  // caller is driving the figure) and when the reader has asked for reduced
  // motion (there is no moving signal to stay in step with).
  const cycling = !active && list.length > 1;
  const stillPreferred =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    if (!cycling || stillPreferred) return;
    const id = window.setInterval(() => setGen((g) => (g + 1) % list.length), 7000);
    return () => window.clearInterval(id);
  }, [cycling, stillPreferred, list.length]);

  const shown = list.length
    ? cycling && !stillPreferred
      ? list[gen % list.length]
      : list[list.length - 1]
    : null;

  return (
    <svg
      width="100%"
      viewBox="0 0 480 360"
      role="img"
      aria-label="The AEGIS closed loop: six stages, two GenAI reasoning points"
      style={{ display: "block", overflow: "visible" }}
    >
      <title>AEGIS closed loop — six stages, two GenAI reasoning points</title>
      <desc>
        Identify produces an attack blueprint, generate produces a synthetic campaign, defend
        produces risk scores, evaluate splits caught from escaped, evolve produces a bounded
        mutation, and retrain produces the next-generation detector which feeds back into identify.
        GenAI reasons at identify and evolve only.
      </desc>

      <defs>
        <marker
          id="nodeloop-arrow"
          viewBox="0 0 8 8"
          refX="6.5"
          refY="4"
          markerWidth="6"
          markerHeight="6"
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M1.5 1.2 6.5 4 1.5 6.8Z" fill="var(--color-border-strong)" />
        </marker>
        <marker
          id="nodeloop-arrow-close"
          viewBox="0 0 8 8"
          refX="6.5"
          refY="4"
          markerWidth="7"
          markerHeight="7"
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M1.5 1.2 6.5 4 1.5 6.8Z" fill="var(--color-accent-500)" />
        </marker>
      </defs>

      <circle
        cx="240"
        cy="186"
        r="66"
        fill="var(--color-surface-sunken)"
        stroke="var(--color-border)"
        strokeWidth="0.75"
      />

      {EDGES.map((d) => (
        <path
          key={d}
          d={d}
          fill="none"
          stroke="var(--color-border-strong)"
          strokeWidth="0.75"
          strokeLinecap="round"
          markerEnd="url(#nodeloop-arrow)"
        />
      ))}
      <path
        d={CLOSING_EDGE}
        fill="none"
        stroke="var(--color-accent-500)"
        strokeWidth="1"
        strokeDasharray="4 3"
        strokeLinecap="round"
        markerEnd="url(#nodeloop-arrow-close)"
      />

      {/* The signal. Red while an attack is in flight, green once it has become
          hardening data. Suppressed under prefers-reduced-motion by the CSS. */}
      <circle
        className="aegis-signal-dot"
        cx="0"
        cy="0"
        r="4.5"
        fill="var(--color-risk-high-600)"
      />

      {/* GenAI reasoning markers -- 2 of 6, and never a number. */}
      {NODES.filter((n) => n.genai).map((n) => (
        <circle
          key={`genai-${n.id}`}
          cx={n.cx}
          cy={n.cy}
          r="29"
          fill="none"
          stroke="var(--color-accent-500)"
          strokeWidth="0.75"
          strokeDasharray="2 4"
          opacity="0.85"
        />
      ))}

      {NODES.map((n) => (
        <g key={n.id}>
          {active === n.id && (
            <circle
              cx={n.cx}
              cy={n.cy}
              r={n.genai ? 34 : 26}
              fill="none"
              stroke="var(--color-ink)"
              strokeWidth="1.25"
            />
          )}
          <circle
            cx={n.cx}
            cy={n.cy}
            r="22"
            fill={TEAM_FILL[n.team]}
            stroke={n.team === "neutral" ? "var(--color-border-strong)" : "var(--color-surface)"}
            strokeWidth={n.team === "neutral" ? 1.25 : 1}
          />
          <text
            x={n.cx}
            y={n.cy + 4.5}
            textAnchor="middle"
            fontSize="12"
            fontWeight="600"
            fill={n.team === "neutral" ? "var(--color-ink-muted)" : "#ffffff"}
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {n.n}
          </text>

          <text
            x={n.tx}
            y={n.ty}
            textAnchor={n.anchor}
            fontSize="14"
            fontWeight="600"
            fill="var(--color-ink)"
          >
            {n.title}
          </text>
          {n.sub?.map((line, i) => (
            <text
              key={line}
              x={n.tx}
              y={
                n.subAbove
                  ? n.ty - 15 * ((n.sub?.length ?? 1) - i)
                  : n.ty + 15 + i * 15
              }
              textAnchor={n.anchor}
              fontSize="12"
              fill="var(--color-ink-muted)"
            >
              {line}
            </text>
          ))}
        </g>
      ))}

      {/* Centre: the defender generation currently in view. Empty unless real
          figures were passed in. */}
      <foreignObject x="166" y="130" width="148" height="112">
        <div
          style={{
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "var(--font-sans)",
          }}
        >
          {shown ? (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minWidth: 38,
                  height: 19,
                  padding: "0 6px",
                  border: "0.75px solid var(--color-accent-600)",
                  borderRadius: 5,
                  background: "var(--color-surface)",
                  fontSize: "11.5px",
                  fontWeight: 600,
                  lineHeight: 1,
                  color: "var(--color-accent-600)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {shown.label}
              </div>
              <div
                style={{
                  width: 72,
                  height: 1,
                  background: "var(--color-border)",
                  margin: "6px 0",
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {[
                  ["precision", shown.precision],
                  ["recall", shown.recall],
                  ["fpr", shown.fpr],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", alignItems: "baseline", gap: 8, lineHeight: 1 }}>
                    <div
                      style={{
                        width: 52,
                        textAlign: "right",
                        fontSize: "10px",
                        color: "var(--color-ink-faint)",
                      }}
                    >
                      {k}
                    </div>
                    <div
                      style={{
                        width: 46,
                        fontSize: "11px",
                        color: "var(--color-ink)",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {v}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}
          <div
            style={{
              marginTop: shown ? 8 : 0,
              textAlign: "center",
              fontSize: "9px",
              lineHeight: 1.32,
              color: "var(--color-ink-faint)",
            }}
          >
            <div>closed loop —</div>
            <div>evasions become</div>
            <div>training data</div>
          </div>
        </div>
      </foreignObject>
    </svg>
  );
}

/** Reading key for the ring. Kept beside it rather than inside so the figure
 *  can stand alone where space is tight. */
export function NodeLoopLegend() {
  const rows: { swatch: React.ReactNode; text: string }[] = [
    {
      swatch: <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-attack-600)]" />,
      text: "Red team — identify, generate, evolve",
    },
    {
      swatch: <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--color-defend-600)]" />,
      text: "Blue team — defend, retrain",
    },
    {
      swatch: (
        <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)]" />
      ),
      text: "Neutral — evaluate",
    },
    {
      swatch: (
        <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-dashed border-[var(--color-accent-500)]" />
      ),
      text: "GenAI reasoning point — 2 of 6, never emits a number",
    },
    {
      swatch: (
        <span className="h-0 w-2.5 shrink-0 border-t border-dashed border-[var(--color-accent-500)]" />
      ),
      text: "Loop closes — retrain feeds identify",
    },
    {
      swatch: (
        <span className="flex shrink-0 gap-0.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-risk-high-600)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-risk-low-600)]" />
        </span>
      ),
      text: "Signal — attack in flight, then hardening data",
    },
  ];

  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {rows.map((r) => (
        <li key={r.text} className="t-body-sm flex items-center gap-2.5 text-[var(--color-ink-muted)]">
          {r.swatch}
          <span>{r.text}</span>
        </li>
      ))}
    </ul>
  );
}
