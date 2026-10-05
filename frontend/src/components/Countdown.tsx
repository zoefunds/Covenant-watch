"use client";

import { useEffect, useState } from "react";
import { formatDuration } from "@/lib/format";
import { getCurrentTime } from "@/lib/contract";

export function secondsUntil(targetTs: number, nowMs = Date.now()): number {
  return Math.max(0, Math.ceil(targetTs - nowMs / 1000));
}

export function useContractClock(): number {
  const [offsetSeconds, setOffsetSeconds] = useState(0);
  const [nowTs, setNowTs] = useState(() => Date.now() / 1000);

  useEffect(() => {
    let cancelled = false;
    getCurrentTime()
      .then((chainNow) => {
        if (!cancelled) setOffsetSeconds(Number(chainNow) - Date.now() / 1000);
      })
      .catch(() => {
        // Contract remains authoritative if the synchronization read fails;
        // the local clock is only a temporary UX fallback.
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const tick = () => setNowTs(Date.now() / 1000 + offsetSeconds);
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [offsetSeconds]);

  return nowTs;
}

export function useCountdown(targetTs: number, nowTs?: number): number {
  const [remaining, setRemaining] = useState(() => secondsUntil(targetTs));

  useEffect(() => {
    const tick = () => setRemaining(Math.max(0, Math.ceil(targetTs - (nowTs ?? Date.now() / 1000))));
    tick();
    if (nowTs !== undefined) return;
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [targetTs, nowTs]);

  return remaining;
}

export function Countdown({ targetTs, elapsedLabel = "Elapsed", nowTs }: { targetTs: number; elapsedLabel?: string; nowTs?: number }) {
  const remaining = useCountdown(targetTs, nowTs);
  return <span>{remaining > 0 ? formatDuration(remaining) : elapsedLabel}</span>;
}
