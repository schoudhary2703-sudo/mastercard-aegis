import type { SVGProps } from "react";

const base: SVGProps<SVGSVGElement> = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
};

export const OverviewIcon = () => (
  <svg {...base}>
    <rect x="3" y="3" width="8" height="8" rx="1.5" />
    <rect x="13" y="3" width="8" height="5" rx="1.5" />
    <rect x="13" y="10" width="8" height="11" rx="1.5" />
    <rect x="3" y="13" width="8" height="8" rx="1.5" />
  </svg>
);

export const StudioIcon = () => (
  <svg {...base}>
    <path d="M9 3v6L4 19a1.5 1.5 0 0 0 1.3 2.2h13.4A1.5 1.5 0 0 0 20 19l-5-10V3" />
    <path d="M7 3h10" />
    <path d="M8 15h8" />
  </svg>
);

export const DetectionIcon = () => (
  <svg {...base}>
    <path d="M12 3l7 3v6c0 4.4-3 7.8-7 9-4-1.2-7-4.6-7-9V6l7-3z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const LoopIcon = () => (
  <svg {...base}>
    <path d="M4 12a8 8 0 0 1 13.66-5.66L20 8" />
    <path d="M20 4v4h-4" />
    <path d="M20 12a8 8 0 0 1-13.66 5.66L4 16" />
    <path d="M4 20v-4h4" />
  </svg>
);

export const TaxonomyIcon = () => (
  <svg {...base}>
    <path d="M12 3v6" />
    <circle cx="12" cy="4.5" r="1.5" />
    <circle cx="5" cy="19.5" r="1.5" />
    <circle cx="12" cy="19.5" r="1.5" />
    <circle cx="19" cy="19.5" r="1.5" />
    <path d="M12 9c-3 0-3 8.5-7 9.5M12 9c0 4 0 9.5 0 9.5M12 9c3 0 3 8.5 7 9.5" />
  </svg>
);

export const EvaluationIcon = () => (
  <svg {...base}>
    <path d="M4 20V10M11 20V4M18 20v-7" />
    <path d="M2 20h20" />
  </svg>
);

export const BenchmarkIcon = () => (
  <svg {...base}>
    <circle cx="12" cy="9" r="6" />
    <path d="M8.5 14.2 7 21l5-2.5L17 21l-1.5-6.8" />
  </svg>
);

export const ResetIcon = () => (
  <svg {...base} width={15} height={15}>
    <path d="M4 12a8 8 0 1 0 2.5-5.8" />
    <path d="M4 3v4h4" />
  </svg>
);

export const MenuIcon = () => (
  <svg {...base} width={18} height={18}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </svg>
);
