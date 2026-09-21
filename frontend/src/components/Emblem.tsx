// Obsidian-Assurance emblem: a pinned/locked seal motif (a hexagonal
// ledger seal with a central lock-pin) rebuilt clean in SVG rather than
// pulled from the raw prototype file, per the working rules.
export function Emblem({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="Covenant Watch"
    >
      <path
        d="M24 3 L43 13.5 V34.5 L24 45 L5 34.5 V13.5 Z"
        stroke="#00F0FF"
        strokeWidth="2"
        fill="#0d1c2d"
      />
      <path
        d="M24 10 L36.5 17 V31 L24 38 L11.5 31 V17 Z"
        stroke="#00DBE9"
        strokeWidth="1.2"
        fill="#122131"
        opacity="0.9"
      />
      <circle cx="24" cy="24" r="5.5" fill="#00F0FF" opacity="0.9" />
      <path d="M24 19.5 V16.5 M24 31.5 V28.5" stroke="#051424" strokeWidth="1.4" />
      <circle cx="24" cy="24" r="2" fill="#051424" />
    </svg>
  );
}
