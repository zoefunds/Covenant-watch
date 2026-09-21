// Obsidian-Assurance emblem: a hexagonal shield with a concentric
// "watch iris" and reticle crossbars — a clean SVG rebuild of the mark
// defined in covenant_watch_emblem.html (the sanctioned prototype
// source for this asset), redrawn on a 0-48 grid and recolored to the
// Obsidian Assurance design tokens rather than copied byte-for-byte.
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
      <defs>
        <linearGradient id="cwGlow" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00F0FF" />
          <stop offset="100%" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      {/* Outer shield hexagon */}
      <polygon
        points="24,5 42,13.5 42,32.5 24,44 6,32.5 6,13.5"
        stroke="url(#cwGlow)"
        strokeWidth="1.8"
        fill="#0d1c2d"
      />
      {/* Concentric covenant rings / validator orbit */}
      <circle cx="24" cy="24" r="10.5" stroke="#2A364F" strokeWidth="1" strokeDasharray="2 1.6" />
      <circle cx="24" cy="24" r="6.2" stroke="#00F0FF" strokeWidth="1.2" />
      {/* Center watch iris / onchain proof node */}
      <circle cx="24" cy="24" r="2.4" fill="#00F0FF" />
      {/* Satellite validator nodes */}
      <circle cx="24" cy="13.5" r="1.4" fill="#3B82F6" />
      <circle cx="33.1" cy="29.3" r="1.4" fill="#3B82F6" />
      <circle cx="14.9" cy="29.3" r="1.4" fill="#3B82F6" />
      {/* Reticle crossbars */}
      <line x1="24" y1="9.6" x2="24" y2="11.5" stroke="#00F0FF" strokeWidth="1" strokeLinecap="round" />
      <line x1="24" y1="36.5" x2="24" y2="38.4" stroke="#00F0FF" strokeWidth="1" strokeLinecap="round" />
      <line x1="11.5" y1="24" x2="13.4" y2="24" stroke="#00F0FF" strokeWidth="1" strokeLinecap="round" />
      <line x1="34.6" y1="24" x2="36.5" y2="24" stroke="#00F0FF" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}
