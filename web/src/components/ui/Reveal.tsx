import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** Never leave content invisible: reveal regardless if the observer stays quiet. */
const FAILSAFE_MS = 1200;

/**
 * Fades a section in the first time it enters the viewport, once.
 *
 * Uses a callback ref rather than `useRef` + mount effect: these sections are
 * rendered inside API-state render props, so React can swap the underlying
 * node when the request resolves. A mount-only effect would then be observing
 * a detached element and the content would never appear.
 */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const [shown, setShown] = useState(false);
  const observer = useRef<IntersectionObserver | null>(null);

  const attach = useCallback(
    (node: HTMLDivElement | null) => {
      observer.current?.disconnect();
      if (!node || shown) return;
      if (typeof IntersectionObserver === "undefined") {
        setShown(true);
        return;
      }
      observer.current = new IntersectionObserver(
        (entries) => {
          if (!entries.some((e) => e.isIntersecting)) return;
          setShown(true);
          observer.current?.disconnect();
        },
        { rootMargin: "0px 0px -6% 0px", threshold: 0.02 },
      );
      observer.current.observe(node);
    },
    [shown],
  );

  useEffect(() => {
    const timer = setTimeout(() => setShown(true), FAILSAFE_MS);
    return () => {
      clearTimeout(timer);
      observer.current?.disconnect();
    };
  }, []);

  return (
    <div
      ref={attach}
      className={`reveal ${shown ? "reveal--in" : ""} ${className}`}
      style={shown && delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
