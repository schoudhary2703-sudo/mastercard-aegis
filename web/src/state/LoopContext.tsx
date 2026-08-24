import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { runRound, type RoundRecord } from "../mock/loopSimulator";
import type { AttackFamily } from "../types/aegis";

interface LoopState {
  family: AttackFamily;
  rounds: RoundRecord[];
  setFamily: (family: AttackFamily) => void;
  runNextRound: () => void;
  reset: () => void;
  latest: RoundRecord | null;
}

const LoopContext = createContext<LoopState | null>(null);

export function LoopProvider({ children }: { children: ReactNode }) {
  const [family, setFamilyState] = useState<AttackFamily>("synthetic_identity_bustout");
  const [rounds, setRounds] = useState<RoundRecord[]>([]);

  const setFamily = useCallback((next: AttackFamily) => {
    setFamilyState(next);
    setRounds([]);
  }, []);

  const runNextRound = useCallback(() => {
    setRounds((prev) => {
      if (prev.length >= 6) return prev;
      const record = runRound(family, prev[prev.length - 1] ?? null);
      return [...prev, record];
    });
  }, [family]);

  const reset = useCallback(() => setRounds([]), []);

  const value = useMemo(
    () => ({ family, rounds, setFamily, runNextRound, reset, latest: rounds[rounds.length - 1] ?? null }),
    [family, rounds, setFamily, runNextRound, reset],
  );

  return <LoopContext.Provider value={value}>{children}</LoopContext.Provider>;
}

export function useLoop(): LoopState {
  const ctx = useContext(LoopContext);
  if (!ctx) throw new Error("useLoop must be used within LoopProvider");
  return ctx;
}
