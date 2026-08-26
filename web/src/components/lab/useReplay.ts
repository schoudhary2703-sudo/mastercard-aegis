import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ExperimentDTO, ReplayEventDTO } from "../../api/types";

/**
 * Steps through an experiment's already-persisted events on a timer.
 *
 * This is a *replay*, not a simulation: every event was scored by a real
 * detector in a run that already happened, and the only thing this hook adds
 * is the pacing. It computes no risk scores and no verdicts -- `caught` comes
 * off the artifact. Counters are derived by counting revealed events, so they
 * can never disagree with the rows on screen.
 */

const TICK_MS = 320;

export interface ReplayCounters {
  revealed: number;
  totalEvents: number;
  fraudSeen: number;
  caught: number;
  escaped: number;
  recall: number | null;
}

export function useReplay(experiment: ExperimentDTO | null) {
  const events = useMemo<ReplayEventDTO[]>(() => experiment?.events ?? [], [experiment]);
  const [cursor, setCursor] = useState(0);
  const [running, setRunning] = useState(false);
  const timer = useRef<number | null>(null);

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  // A new experiment resets the replay rather than continuing mid-stream.
  useEffect(() => {
    clear();
    setCursor(0);
    setRunning(false);
  }, [experiment?.attack_family, clear]);

  useEffect(() => {
    if (!running) return;
    if (cursor >= events.length) {
      setRunning(false);
      return;
    }
    timer.current = window.setTimeout(() => setCursor((c) => c + 1), TICK_MS);
    return clear;
  }, [running, cursor, events.length, clear]);

  useEffect(() => clear, [clear]);

  const start = useCallback(() => {
    if (events.length === 0) return;
    setCursor(0);
    setRunning(true);
  }, [events.length]);

  const stop = useCallback(() => setRunning(false), []);

  const showAll = useCallback(() => {
    clear();
    setRunning(false);
    setCursor(events.length);
  }, [events.length, clear]);

  const revealed = useMemo(() => events.slice(0, cursor), [events, cursor]);

  const counters = useMemo<ReplayCounters>(() => {
    const fraud = revealed.filter((e) => e.is_fraud);
    const caught = fraud.filter((e) => e.caught).length;
    return {
      revealed: revealed.length,
      totalEvents: events.length,
      fraudSeen: fraud.length,
      caught,
      escaped: fraud.length - caught,
      recall: fraud.length > 0 ? caught / fraud.length : null,
    };
  }, [revealed, events.length]);

  return {
    revealed,
    counters,
    running,
    finished: cursor >= events.length && cursor > 0,
    started: cursor > 0,
    start,
    stop,
    showAll,
  };
}
