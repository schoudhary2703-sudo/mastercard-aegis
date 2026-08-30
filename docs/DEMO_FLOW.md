# Demo flow

A 4-6 minute judge walkthrough. Every number spoken here is real, read live
from the running API -- nothing in this script is a mock number or an
invented figure. Start both servers first (`docs/DEPLOYMENT.md` "Local
demo" or `README.md` "How to run locally"); confirm `GET /api/health`
returns `{"status": "ok"}` before judges arrive.

Say the word **"real"** or **"simulated"** every time you point at a number
-- the UI already labels every section, but say it out loud too.

---

## 0. Opening (30s)

> "Fraud detectors trained once and left alone go stale, because attackers
> adapt. Most demos show a static model on a static test set. AEGIS is a
> closed-loop red-team / blue-team system that's actually run that loop for
> real: a Red Team generates fraud, a Blue Team detects it, and we've
> measured -- honestly, including where it didn't work -- whether hardening
> against attacks it's seen generalizes to attacks it hasn't."

Open `/` (Overview).

## 1. Overview (30s)

The hero, the closed-loop diagram and "Where AEGIS fits" are **static** --
they render before any API call resolves, so this section works even on a
cold backend. Read the headline, then point at the mechanism strip.

> "Stress-test fraud models against attacks they haven't learned yet.
> GenAI reasons, deterministic code generates every transaction, XGBoost
> detects, and whatever escapes becomes the next red team's signal."

Point at the **closed loop** below it -- eight stages, amber for Red Team,
blue for Blue Team, a filled dot on the two stages where a language model
reasons.

> "GenAI reasons at exactly two points and never writes a transaction row.
> The simulator does, deterministically, from a seed. And note stage 7 --
> the mutation proposal is bounded: out-of-range proposals are rejected,
> not clamped."

Point at the **LOAFO** callout underneath the loop.

> "And this is separate -- not another loop stage. We hold one attack
> family out of training entirely and ask whether hardening transfers to
> an attack the model has never seen."

Then the three evidence cards, each read from its own endpoint.

> "14 attack vectors identified, 3 deeply simulated -- and we keep that
> distinction everywhere. 55,000 synthetic transactions, seed-reproducible.
> All three families have live GenAI evidence. Defender v3: PR-AUC 0.904,
> 85.2% recall at a 0.1% false-positive budget, 0.0216% FPR. And LOAFO mean
> recall 58.3%, labelled *partial* generalization -- which is the honest
> answer, not the flattering one."

## 2. Attack Taxonomy (30-45s)

Navigate to `/attack-taxonomy`.

> "Three attack families, deliberately fixed: synthetic identity bust-out,
> mule-network structuring, adaptive detector evasion."

Click into the "Real attacks observed" panel, select
`synthetic-identity-bustout-v1`.

> "This is a real generated blueprint, its behavioral sequence, and every
> real confrontation it's been scored against -- including the fidelity and
> hardness of the transactions that got through."

## 3. Round-0: the blind spot (30s)

Navigate to `/co-evolution`. Point at the **Round-0 attack** card in the
real closed-loop timeline.

> "Baseline v1's very first confrontation: 0 of 3 fraudulent bust-out
> transactions caught. That's the blind spot we're closing."

## 4. Defender hardening (30-45s)

Point at the **Defender v2 hardening** and **Fresh Defender-v2 confrontation**
cards, then read the narrative panel underneath.

> "Defender v2 promotes those false negatives into training. On a brand-new
> bust-out scenario it had never seen, it catches 2 of 3 -- but on the
> native PaySim test set, F1 actually dropped 1.36 points versus baseline.
> Hardening against one family isn't free."

## 5. Cross-family results (45s)

Navigate to `/final-benchmark`. Point at the **Model comparison** cards.

> "Defender v3 trains on hard positives from all three families at once,
> plus two new features -- distinct-counterparty counts -- added specifically
> because the mule-network data showed the original 19 features literally
> can't tell a fan-out payment from six repeat payments to the same account."

Point at the comparison table.

> "F1 recovers to 85.1%, precision improves to 93.8%, and false-positive
> rate drops to 0.0216% -- v3's best FPR of the three. It still doesn't
> fully recover v1's recall. We're not hiding that."

## 6. LOAFO: generalization, not memorization (45-60s)

Point at the **Defender v3 recall by attack family** chart, then the LOAFO
table below it.

> "Here's the question that actually matters: if we train on two families
> and hide the third completely -- zero training rows -- does hardening
> transfer, or was v3 just memorizing? Bust-out and adaptive-evasion
> transfer strongly: 100% and 75% recall on a completely fresh, never-seen
> scenario. Mule-network structuring: zero. Trained on the other two
> families, it catches nothing on a fresh mule scenario, even though
> Defender v3 -- which *did* train on mule data -- catches 42% of the same
> scenario. Mean LOAFO recall is 58%. That's a real, partial result, and
> we're reporting the weak case, not just the two strong ones."

## 7. Hardest surviving attacks (30s)

Scroll to the **Hardest surviving attacks** table on the same page.

> "Every one of these is a real fraudulent transaction that evaded a real
> detector in this benchmark, ranked by hardness -- transaction id, family,
> risk score, fidelity, which model, whether it survived."

## 8. Final Benchmark summary (30s)

Scroll to the bottom of `/final-benchmark` and expand the collapsed
**"Interpretation and limitations"** section.

> "This text isn't written by us -- it's assembled from the same numbers
> you just saw: the F1 delta, the LOAFO verdict, the weakest family. And it
> ends the same way every honest read of this data has to: not a claim of
> universal fraud detection."

## 9. Closing takeaway (20-30s)

> "AEGIS didn't just train one model and report its accuracy. It ran a real
> closed loop across three defender generations, tested cross-family
> hardening, and then specifically tested whether that hardening
> generalizes to attacks it never saw -- and found a real, mixed answer:
> strong for two families, weak for one. That honesty is the point."

---

## If something breaks

* **API unreachable:** every real section shows an explicit "Could not
  reach the AEGIS API" error, not a silent fallback or a fake number. Say
  so, restart the API (`docs/DEPLOYMENT.md`), reload.
* **A real section is empty:** it means that artifact hasn't been produced
  in the current `AEGIS_ARTIFACTS_ROOT` -- confirm the API's artifacts root
  points at a directory containing `models/` and `data/reports/` (see
  `docs/DEPLOYMENT.md` "Artifact expectations"). The mock demo pages
  (Co-Evolution's "interactive demo" panel, Attack Studio's generator) keep
  working regardless -- fall back to those to keep the room engaged while
  you fix it.
* **Time is short:** cut section 2 (Attack Taxonomy) and section 3
  (Round-0) -- sections 5, 6, and 9 (cross-family, LOAFO, closing) carry the
  actual finding.
