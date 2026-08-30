import { useEffect, useRef, useState } from "react";

const DURATION = 620;

/**
 * Counts a metric up to its value once on mount. Respects reduced motion by
 * rendering the final value immediately -- the number is the content, the
 * animation is only there to draw the eye to it on arrival.
 */
export function CountUp({
  value,
  format,
  className = "",
}: {
  value: number | null | undefined;
  format: (n: number) => string;
  className?: string;
}) {
  const [display, setDisplay] = useState(value ?? 0);
  const frame = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (value == null) return;
    const reduced =
      typeof matchMedia !== "undefined" &&
      matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setDisplay(value);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      // ease-out cubic: fast arrival, gentle settle
      setDisplay(value * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [value]);

  if (value == null) return <span className={className}>—</span>;
  return <span className={className}>{format(display)}</span>;
}
