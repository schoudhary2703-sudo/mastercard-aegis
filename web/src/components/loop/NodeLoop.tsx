import { useCallback, useState } from "react";

/**
 * The AEGIS closed loop as one animated figure.
 *
 * Six stages on a ring, numbered in execution order. Red-team stages are
 * amber, blue-team stages teal, evaluation neutral. The two GenAI reasoning
 * points (identify, evolve) carry a dashed halo -- that split is the
 * architectural claim this project makes, so the picture has to carry it.
 *
 * A signal dot travels the ring: red on the way out (an attack in flight),
 * green after evaluation (the same attack, now hardening data). Each full
 * lap advances the centre readout v1 -> v2 -> v3, which is the whole story
 * in one motion.
 *
 * Geometry is precomputed, not derived at render: the label anchors differ
 * per node and hand-placing them is what keeps the figure clean.
 */

export type LoopStageId =
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

/** Real figures from `regression_vs_v1_v2.json` on the untouched test split. */
const GENERATIONS: LoopGeneration[] = [
  { label: "v1", precision: "92.9%", recall: "79.5%", fpr: "0.025%" },
  { label: "v2", precision: "93.1%", recall: "77.1%", fpr: "0.024%" },
  { label: "v3", precision: "93.8%", recall: "77.9%", fpr: "0.022%" },
];

type Team = "attack" | "defend" | "neutral";
type Anchor = "start" | "middle" | "end";

interface Node {
  id: LoopStageId;
  n: number;
  label: string;
  produces: string[];
  team: Team;
  genai?: boolean;
  /** hero geometry */
  x: number;
  y: number;
  tx: number;
  ty: number;
  anchor: Anchor;
  /** compact geometry */
  cx: number;
  cy: number;
  ctx: number;
  cty: number;
  canchor: Anchor;
}

const NODES: Node[] = [
  {
    id: "identify", n: 1, label: "Identify", produces: ["attack blueprint"],
    team: "attack", genai: true,
    x: 240, y: 82, tx: 240, ty: 50, anchor: "middle",
    cx: 150, cy: 46, ctx: 150, cty: 22, canchor: "middle",
  },
  {
    id: "generate", n: 2, label: "Generate", produces: ["synthetic", "campaign"],
    team: "attack",
    x: 347.38, y: 134, tx: 378.38, ty: 124, anchor: "start",
    cx: 224.48, cy: 80, ctx: 247.48, cty: 85, canchor: "start",
  },
  {
    id: "defend", n: 3, label: "Defend", produces: ["risk scores"],
    team: "defend",
    x: 347.38, y: 238, tx: 378.38, ty: 235.5, anchor: "start",
    cx: 224.48, cy: 148, ctx: 247.48, cty: 153, canchor: "start",
  },
  {
    id: "evaluate", n: 4, label: "Evaluate", produces: ["caught / escaped"],
    team: "neutral",
    x: 240, y: 290, tx: 240, ty: 330, anchor: "middle",
    cx: 150, cy: 182, ctx: 150, cty: 213, canchor: "middle",
  },
  {
    id: "evolve", n: 5, label: "Evolve", produces: ["bounded", "mutation"],
    team: "attack", genai: true,
    x: 132.62, y: 238, tx: 101.62, ty: 228, anchor: "end",
    cx: 75.52, cy: 148, ctx: 52.52, cty: 153, canchor: "end",
  },
  {
    id: "retrain", n: 6, label: "Retrain", produces: ["next-gen", "detector"],
    team: "defend",
    x: 132.62, y: 134, tx: 101.62, ty: 124, anchor: "end",
    cx: 75.52, cy: 80, ctx: 52.52, cty: 85, canchor: "end",
  },
];

const TEAM_FILL: Record<Team, string> = {
  attack: "var(--color-attack-600)",
  defend: "var(--color-defend-600)",
  neutral: "var(--color-surface)",
};

/** Connector arcs, in ring order. The last one closes the loop. */
const HERO_EDGES = [
  "M272.09 85.55Q305.72 90.53 327.68 112.46",
  "M359.77 159.08Q371.44 186 359.77 212.92",
  "M327.68 259.54Q305.72 281.47 272.09 286.45",
  "M207.91 286.45Q174.28 281.47 152.32 259.54",
  "M120.23 212.92Q108.56 186 120.23 159.08",
];
const HERO_CLOSING = "M152.32 112.46Q174.28 90.53 207.91 85.55";

const COMPACT_EDGES = [
  "M172.26 48.32Q195.58 51.58 210.81 65.92",
  "M233.07 96.4Q241.16 114 233.07 131.6",
  "M210.81 162.08Q195.58 176.42 172.26 179.68",
  "M127.74 179.68Q104.42 176.42 89.19 162.08",
  "M66.93 131.6Q58.84 114 66.93 96.4",
];
const COMPACT_CLOSING = "M89.19 65.92Q104.42 51.58 127.74 48.32";

const SIGNAL_PATH = "M240 82A124 104 0 0 1 240 290A124 104 0 0 1 240 82";

function Markers({ idPrefix }: { idPrefix: string }) {
  return (
    <defs>
      <marker
        id={`${idPrefix}-arrow`}
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
        id={`${idPrefix}-arrow-close`}
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
  );
}

export function NodeLoop({
  active,
  compact = false,
  className = "",
}: {
  active?: LoopStageId;
  compact?: boolean;
  className?: string;
}) {
  const [gen, setGen] = useState(0);

  // A pinned stage means a replay is driving the figure -- freeze the readout
  // on the current defender rather than cycling underneath the narration.
  const pinned = Boolean(active);
  const g = GENERATIONS[pinned ? GENERATIONS.length - 1 : gen] ?? GENERATIONS[0];

  const onIteration = useCallback(
    (event: React.AnimationEvent<SVGCircleElement>) => {
      // Two animations share this element; only the ring lap advances a generation.
      if (event.animationName !== "aegis-signal") return;
      setGen((current) => (current + 1) % GENERATIONS.length);
    },
    [],
  );

  const describe =
    "Six stages run clockwise: identify produces an attack blueprint, generate produces a " +
    "synthetic campaign, defend produces risk scores, evaluate splits caught from escaped, " +
    "evolve produces a bounded mutation, and retrain produces the next-generation detector, " +
    "which feeds back into identify. GenAI reasons at identify and evolve only." +
    (active ? ` Currently highlighting the ${active} stage.` : "");

  if (compact) {
    return (
      <svg
        width="100%"
        viewBox="0 0 300 220"
        role="img"
        className={`block overflow-visible ${className}`}
      >
        <title>AEGIS closed loop</title>
        <desc>{describe}</desc>
        <Markers idPrefix="loop-c" />

        <circle
          cx="150" cy="114" r="42"
          fill="var(--color-surface-sunken)"
          stroke="var(--color-border)" strokeWidth="0.75"
        />

        {COMPACT_EDGES.map((d) => (
          <path
            key={d} d={d} fill="none"
            stroke="var(--color-border-strong)" strokeWidth="0.75" strokeLinecap="round"
            markerEnd="url(#loop-c-arrow)"
          />
        ))}
        <path
          d={COMPACT_CLOSING} fill="none"
          stroke="var(--color-accent-500)" strokeWidth="1"
          strokeDasharray="4 3" strokeLinecap="round"
          markerEnd="url(#loop-c-arrow-close)"
        />

        {NODES.filter((n) => n.genai).map((n) => (
          <circle
            key={`halo-${n.id}`} cx={n.cx} cy={n.cy} r="22"
            fill="none" stroke="var(--color-accent-500)"
            strokeWidth="0.75" strokeDasharray="2 4" opacity="0.8"
          />
        ))}

        {NODES.map((n) => (
          <g key={n.id}>
            {active === n.id && (
              <circle
                cx={n.cx} cy={n.cy} r={n.genai ? 24 : 19}
                fill="none" stroke="var(--color-ink)" strokeWidth="1"
              />
            )}
            <circle
              cx={n.cx} cy={n.cy} r="15"
              fill={TEAM_FILL[n.team]}
              fillOpacity={n.team === "neutral" ? 1 : 0.85}
              stroke={n.team === "neutral" ? "var(--color-border-strong)" : "var(--color-canvas)"}
              strokeWidth={n.team === "neutral" ? 1 : 0.75}
            />
            <text
              x={n.cx} y={n.cy + 3.5} textAnchor="middle"
              fontSize="10" fontWeight="600"
              fill={n.team === "neutral" ? "var(--color-ink-muted)" : "var(--color-canvas)"}
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {n.n}
            </text>
            <text
              x={n.ctx} y={n.cty} textAnchor={n.canchor}
              fontSize="11" fontWeight="600" fill="var(--color-ink)"
            >
              {n.genai ? `◆ ${n.label}` : n.label}
            </text>
          </g>
        ))}
      </svg>
    );
  }

  return (
    <svg
      width="100%"
      viewBox="0 0 480 360"
      role="img"
      className={`block overflow-visible ${className}`}
    >
      <title>AEGIS closed loop — six stages, two GenAI reasoning points</title>
      <desc>{describe}</desc>
      <Markers idPrefix="loop-h" />

      <circle
        cx="240" cy="186" r="66"
        fill="var(--color-surface-sunken)"
        stroke="var(--color-border)" strokeWidth="0.75"
      />

      {HERO_EDGES.map((d) => (
        <path
          key={d} d={d} fill="none"
          stroke="var(--color-border-strong)" strokeWidth="0.75" strokeLinecap="round"
          markerEnd="url(#loop-h-arrow)"
        />
      ))}
      <path
        d={HERO_CLOSING} fill="none"
        stroke="var(--color-accent-500)" strokeWidth="1"
        strokeDasharray="4 3" strokeLinecap="round"
        markerEnd="url(#loop-h-arrow-close)"
      />

      {!pinned && (
        <circle
          className="aegis-signal-dot"
          cx="0" cy="0" r="4.5"
          fill="var(--color-risk-high-600)"
          style={{ offsetPath: `path('${SIGNAL_PATH}')` }}
          onAnimationIteration={onIteration}
        />
      )}

      {NODES.filter((n) => n.genai).map((n) => (
        <circle
          key={`halo-${n.id}`} cx={n.x} cy={n.y} r="29"
          fill="none" stroke="var(--color-accent-500)"
          strokeWidth="0.75" strokeDasharray="2 4" opacity="0.8"
        />
      ))}

      {NODES.map((n) => (
        <g key={n.id}>
          {active === n.id && (
            <circle
              cx={n.x} cy={n.y} r={n.genai ? 34 : 26}
              fill="none" stroke="var(--color-ink)" strokeWidth="1"
            />
          )}
          <circle
            cx={n.x} cy={n.y} r="22"
            fill={TEAM_FILL[n.team]}
            stroke={n.team === "neutral" ? "var(--color-border-strong)" : "var(--color-canvas)"}
            strokeWidth={n.team === "neutral" ? 1.25 : 1}
          />
          <text
            x={n.x} y={n.y + 4.5} textAnchor="middle"
            fontSize="12" fontWeight="600"
            fill={n.team === "neutral" ? "var(--color-ink-muted)" : "var(--color-canvas)"}
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {n.n}
          </text>

          {/* Identify and Evaluate label above/below; the flanks label outward. */}
          {n.anchor === "middle" ? (
            <>
              <text
                x={n.tx} y={n.id === "identify" ? n.ty - 15 : n.ty} textAnchor="middle"
                fontSize={n.id === "identify" ? 12 : 14}
                fontWeight={n.id === "identify" ? 400 : 600}
                fill={n.id === "identify" ? "var(--color-ink-muted)" : "var(--color-ink)"}
              >
                {n.id === "identify" ? n.produces[0] : n.label}
              </text>
              <text
                x={n.tx} y={n.id === "identify" ? n.ty : n.ty + 15} textAnchor="middle"
                fontSize={n.id === "identify" ? 14 : 12}
                fontWeight={n.id === "identify" ? 600 : 400}
                fill={n.id === "identify" ? "var(--color-ink)" : "var(--color-ink-muted)"}
              >
                {n.id === "identify" ? n.label : n.produces[0]}
              </text>
            </>
          ) : (
            <>
              <text
                x={n.tx} y={n.ty} textAnchor={n.anchor}
                fontSize="14" fontWeight="600" fill="var(--color-ink)"
              >
                {n.label}
              </text>
              {n.produces.map((line, i) => (
                <text
                  key={line} x={n.tx} y={n.ty + 15 + i * 15} textAnchor={n.anchor}
                  fontSize="12" fill="var(--color-ink-muted)"
                >
                  {line}
                </text>
              ))}
            </>
          )}

          {n.genai && (
            <>
              <rect
                x={n.id === "identify" ? 198 : 17.62}
                y={n.id === "identify" ? 8 : 264}
                width="84" height="15" rx="7.5"
                fill="var(--color-canvas)"
                stroke="var(--color-accent-600)" strokeWidth="0.75" opacity="0.9"
              />
              <text
                x={n.id === "identify" ? 240 : 94.62}
                y={n.id === "identify" ? 18.8 : 274.8}
                textAnchor={n.id === "identify" ? "middle" : "end"}
                fontSize="9.5" fill="var(--color-accent-500)"
              >
                ◆ GenAI reasons
              </text>
            </>
          )}
        </g>
      ))}

      <foreignObject x="166" y="124" width="148" height="124">
        <div className="flex h-full flex-col items-center justify-center">
          <div
            className="flex h-[19px] w-[38px] items-center justify-center rounded-[5px] border border-[var(--color-accent-600)] bg-[var(--color-canvas)] text-[11.5px] font-semibold leading-none text-[var(--color-accent-500)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {g.label}
          </div>
          <div className="my-[5px] h-px w-[72px] bg-[var(--color-border)]" />
          <div className="flex flex-col gap-1">
            {(
              [
                ["precision", g.precision],
                ["recall", g.recall],
                ["fpr", g.fpr],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-2 leading-none">
                <div className="w-[52px] text-right text-[10px] text-[var(--color-ink-faint)]">
                  {k}
                </div>
                <div
                  className="w-[44px] text-[11px] text-[var(--color-ink)]"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {v}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-center text-[9px] leading-[1.32] text-[var(--color-ink-faint)]">
            <div>closed loop —</div>
            <div>evasions become</div>
            <div>training data</div>
          </div>
        </div>
      </foreignObject>
    </svg>
  );
}

/** Compact key for the figure. Used beside the hero on Mission Control. */
export function NodeLoopLegend() {
  const rows: { swatch: React.ReactNode; text: string }[] = [
    {
      swatch: <span className="h-[11px] w-[11px] shrink-0 rounded-full bg-[var(--color-attack-600)]" />,
      text: "Red team — identify, generate, evolve",
    },
    {
      swatch: <span className="h-[11px] w-[11px] shrink-0 rounded-full bg-[var(--color-defend-600)]" />,
      text: "Blue team — defend, retrain",
    },
    {
      swatch: (
        <span className="h-[11px] w-[11px] shrink-0 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)]" />
      ),
      text: "Neutral — evaluate",
    },
    {
      swatch: (
        <span className="h-[11px] w-[11px] shrink-0 rounded-full border border-dashed border-[var(--color-accent-500)]" />
      ),
      text: "GenAI reasoning point — 2 of 6, never emits a number",
    },
    {
      swatch: <span className="h-0 w-[11px] shrink-0 border-t border-dashed border-[var(--color-accent-500)]" />,
      text: "Loop closes — retrain feeds identify",
    },
    {
      swatch: (
        <span className="flex shrink-0 gap-[3px]">
          <span className="h-[11px] w-[11px] rounded-full bg-[var(--color-risk-high-600)]" />
          <span className="h-[11px] w-[11px] rounded-full bg-[var(--color-risk-low-600)]" />
        </span>
      ),
      text: "Signal — attack in flight, then hardening data",
    },
  ];

  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <li key={r.text} className="flex items-center gap-3 text-[12px] leading-snug text-[var(--color-ink-muted)]">
          {r.swatch}
          <span>{r.text}</span>
        </li>
      ))}
    </ul>
  );
}
