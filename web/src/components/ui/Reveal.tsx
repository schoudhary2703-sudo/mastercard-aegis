import { useEffect, useRef, useState, type ReactNode } from "react";

/** Reveal once the element's top is this far into the viewport. */
const TRIGGER_RATIO = 0.94;
/** Last-resort: content is never left invisible, whatever else fails. */
const FAILSAFE_MS = 2500;

/**
 * Fades a section in the first time it scrolls into view, once.
 *
 * Deliberately geometry-based rather than IntersectionObserver. IO proved
 * unreliable in at least one embedded/headless context here -- an independent
 * observer with identical options, on an element demonstrably inside the
 * viewport, never fired -- and an animation that fails by leaving content
 * permanently invisible is far worse than no animation at all.
 * `getBoundingClientRect` on a capture-phase scroll listener has no such
 * failure mode, costs nothing at this scale, and catches scrolling containers
 * (scroll does not bubble, but it does capture) as well as the window.
 *
 * The timer is the final guarantee, not the mechanism: if the element never
 * mounts, never scrolls, or anything else goes wrong, the content still shows.
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
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (shown) return;

    let frame = 0;
    let done = false;

    const reveal = () => {
      if (done) return;
      done = true;
      setShown(true);
    };

    const check = () => {
      frame = 0;
      const node = ref.current;
      if (!node) return;
      const box = node.getBoundingClientRect();
      const viewport = window.innerHeight || document.documentElement.clientHeight;
      // A zero-height viewport means nothing can ever be "in view"; leave it to
      // the failsafe rather than resolving every element as off-screen forever.
      if (viewport <= 0) return;
      if (box.top < viewport * TRIGGER_RATIO && box.bottom > 0) reveal();
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(check);
    };

    check();
    // Capture phase so scrolling containers are caught, not just the window.
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    const failsafe = setTimeout(reveal, FAILSAFE_MS);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      clearTimeout(failsafe);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [shown]);

  return (
    <div
      ref={ref}
      className={`reveal ${shown ? "reveal--in" : ""} ${className}`}
      style={shown && delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
