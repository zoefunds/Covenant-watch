export function shortAddr(addr?: string | null, len = 4): string {
  if (!addr) return "—";
  if (addr.length <= 2 + len * 2) return addr;
  return `${addr.slice(0, 2 + len)}…${addr.slice(-len)}`;
}

const WEI_PER_GEN = 10n ** 18n;

export function formatGen(wei: number | string | bigint | undefined | null, maxDecimals = 4): string {
  if (wei === undefined || wei === null) return "—";
  let big: bigint;
  try {
    big = typeof wei === "bigint" ? wei : BigInt(String(wei));
  } catch {
    return "—";
  }
  const whole = big / WEI_PER_GEN;
  const frac = big % WEI_PER_GEN;
  if (frac === 0n) return `${whole.toString()} GEN`;
  const fracStr = frac.toString().padStart(18, "0").slice(0, maxDecimals).replace(/0+$/, "");
  return fracStr ? `${whole.toString()}.${fracStr} GEN` : `${whole.toString()} GEN`;
}

export function genToWei(gen: string): bigint {
  const [whole, frac = ""] = gen.trim().split(".");
  const fracPadded = (frac + "0".repeat(18)).slice(0, 18);
  const wholeBig = BigInt(whole || "0");
  const fracBig = BigInt(fracPadded || "0");
  return wholeBig * WEI_PER_GEN + fracBig;
}

export function formatBps(bps: number | undefined | null): string {
  if (bps === undefined || bps === null) return "—";
  return `${(bps / 100).toFixed(2)}%`;
}

export function formatDuration(seconds: number): string {
  if (seconds <= 0) return "0s";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (!days && mins) parts.push(`${mins}m`);
  return parts.length ? parts.join(" ") : "<1m";
}

export function formatTs(ts: number | undefined | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

export function relativeToNow(ts: number): string {
  const diff = ts - Math.floor(Date.now() / 1000);
  if (diff <= 0) return "ended";
  return formatDuration(diff) + " remaining";
}
