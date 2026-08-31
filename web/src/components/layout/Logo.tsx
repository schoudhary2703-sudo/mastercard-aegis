/**
 * The AEGIS mark: a shield enclosing a closed loop.
 *
 * The two halves of the name are the two halves of the drawing. An aegis is a
 * shield, and the thing that makes this one different from any other fraud
 * detector is that it does not sit still -- the arrow inside completes a
 * circuit and re-enters where it began, which is the same closed loop the
 * console is built around and the same figure a judge meets on Overview.
 *
 * Monochrome and `currentColor` on purpose: it inherits from whatever it sits
 * in, so the sidebar tile, the mobile drawer and the favicon are one drawing
 * rather than three that drift apart. Kept to three paths, because at 16px in
 * a browser tab anything finer turns to mud.
 */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {/* Shield */}
      <path d="M12 2.4 20 5.4v6c0 4.8-3.3 8.8-8 10.2-4.7-1.4-8-5.4-8-10.2v-6Z" />
      {/* The loop, open at the top so the arrow can re-enter it */}
      <path d="M15.3 8.8a4.3 4.3 0 1 1-4.8-1.2" />
      {/* Arrowhead, closing the circuit */}
      <path d="M12.1 7.0 10.9 8.6 10.1 6.5Z" fill="currentColor" stroke="none" />
    </svg>
  );
}
