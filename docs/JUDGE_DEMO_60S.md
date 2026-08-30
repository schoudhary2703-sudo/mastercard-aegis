# 60-second judge walkthrough

Four screens, four clicks: **Overview → Attack Lab → Evolution → Results**.
Everything on screen is read live from persisted artifacts.

Before you start: open [the demo](https://mastercard-aegis.vercel.app) once
and let it load. The API sleeps on a free tier and can take ~25 seconds to
wake; the hero, closed-loop diagram and "Where AEGIS fits" render immediately
regardless, so you can start talking while the evidence cards fill in.

The longer 4–6 minute version is [`DEMO_FLOW.md`](DEMO_FLOW.md).

---

## The script (~145 words)

### 0–10s · Overview — what AEGIS is

> "Stress-test fraud models against attacks they haven't learned yet. GenAI
> reasons about attacks and blind spots; deterministic code writes every
> transaction; a frozen defender scores them."

*Point at:* the hero, then the mechanism strip beneath it.

### 10–25s · Attack Lab — the confrontation

> "Pick a family. GenAI proposed six bounded mutations here — five applied,
> one rejected by the bounds check, and the rejection is persisted. GenAI
> never writes a transaction row; the simulator does, from a seed."

*Point at:* the family tabs, then the proposed / applied / **rejected** panel.

### 25–40s · Evolution — escapes are the signal

> "These are real transactions a real detector let through. Where the
> experiment promoted them as hard positives, they informed a later hardening
> round. LOAFO entries are evaluation evidence only — they don't feed
> training."

*Point at:* the closed-loop timeline, then the per-family escape rows and
their role labels.

### 40–55s · Results — did hardening transfer?

> "Hold one attack family out of hardening entirely, then score a fresh
> scenario of it. Two of three transferred. Mule-network structuring caught
> zero of twelve. Partial generalization — and we publish the fold that
> failed."

*Point at:* the "Partial generalization" verdict, then the LOAFO table and
the family chart where mule has no held-out bar.

### 55–60s · Where it fits

> "This is offline validation and hardening for fraud-model teams. It is not
> in the authorization path and doesn't score live payments."

*Point at:* the "Where AEGIS fits" panel back on Overview, or say it while
closing.

---

## Say these words

* "**Partial** generalization" — never "generalizes".
* "Synthetic / reference data" — PaySim is a simulator, not real traffic.
* "14 identified, **3 deeply simulated**" — never "14 attacks built".
* "Directional" for any per-family figure (3–12 fraud events each).

## Do not say

* That 58.3% is a fraud-detection or production recall rate — it is the mean
  recall of three held-out fold models on three fresh scenarios.
* That any two scenarios are the same run unless the screen says so. Bust-out
  legitimately reads differently across its guided generation, its recorded
  confrontation and its LOAFO fold, because those are three different
  persisted scenarios; the mule and adaptive replays *are* their LOAFO fold
  scenarios. The UI labels each one — read the label rather than comparing
  the numbers.
* Anything about deployment, customers, or production readiness.

## If the demo fails

Every real section shows an explicit "Could not reach the AEGIS API" error
rather than a fabricated number. The Overview hero, the closed-loop diagram
and "Where AEGIS fits" are static and keep rendering, so the whole system can
still be explained with the backend down. Fallback order: reload → walk
through [`submission/artifacts/data/reports/final_benchmark_summary.json`](../submission/artifacts/data/reports/final_benchmark_summary.json)
directly → screenshots.
