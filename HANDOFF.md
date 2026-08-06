# playertracker — HANDOFF (start here in a fresh chat)

*Written 2026-08-05 from the sessionsync chat, which is staying on sessionsync. Nothing
in the new direction is built yet. This is everything needed to pick it up cold.*

**Reading order:** this file → [`docs/PHYSICAL_TRACKING_PLAN.md`](./docs/PHYSICAL_TRACKING_PLAN.md)
(the design, and the measured numbers behind it) → [`../sessionsync/docs/BIOMECH_HANDOFF.md`](../sessionsync/docs/BIOMECH_HANDOFF.md)
(where the training-side numbers come from and what they are worth) →
[`../sessionsync/docs/CAMERA_OPTIONS.md`](../sessionsync/docs/CAMERA_OPTIONS.md) (why capture
quality is a longitudinal concern) → `../CLAUDE.md`.

## The decision, made

**This project is being repurposed** (Tom, 2026-08-05) from *AUS ODI career progression*
to **tracking a player's physical and technical profile over time**.

Run a session → numbers into a store with screenshots and vision links → reports that
answer *is their speed changing, are they getting more knee flexion, what is their run-up
speed doing*. Then the same off match data, where ball speed, GPS and Hawkeye vision all
line up.

**The ODI career tool is not dead, and it has now MOVED** ✅ (2026-08-06). Its home is the new
sibling **[`../scorecardanalysis`](../scorecardanalysis/)**, per `FUTURE_PROJECTS.md`
§"Scorecard-level analysis" — scorecard-level *analysis* belongs neither in `scorecarddb`
(which pulls) nor here (which is becoming physical tracking). Moved, not destroyed: `app.py`,
`data.py`, `pages/career_progression.py`, `pages/block_analysis.py`,
`scripts/build_player_career.py`, `scripts/build_career_from_scorecard.py` — verified running in
the new home before removal here. **This repo is now clear for the repurpose.**

## Audience: coach, S&C, and individual players

Tom, 2026-08-05. The third one changes things:

- **House language rules apply hard** (`../CLAUDE.md`): "vision" not clips, gender-neutral
  throughout, no unexplained method jargon, explain any percentile in plain words, hedge
  anything predictive. A player reading "your knee flexion is P73" has learned nothing.
- **Access control is a gate, not a feature.** Player physical data is in the same class
  as the medical data `amtmskreport` handles. See `LUDIS.md` on the access-control gate
  before anything is published.
- **Per-player packs**, not one dashboard everyone shares — the same shape as
  playerprofile's individualization front (per-player packs off one link).
- Report the **uncertainty in plain words**. "No change we can detect" is a real and
  useful answer, and the one this data will give most often.

## The two constraints — read these before designing anything

Both measured on 4 Aug across 32 deliveries, reproducible from
`sessionsync/data/merged/2026-08-04_biomech.csv`.

**1. The reportable grain is a session, not a delivery.** 80–100 % of ball-to-ball spread
in these metrics is measurement noise. A single delivery's knee flexion is worth ±6.1°
against real ball-to-ball variation of 2.9°. **Every stored value must carry `se` and
`n`** — a schema requirement, not a display nicety. A store of bare numbers will produce
confident-looking charts of nothing.

**2. Instrument is part of the series identity.** Training and match measure the same
quantity with different devices, and that difference *will* look like the player changing.
Radar vs Hawkeye for speed; a wide training camera vs Hawkeye footage for biomech, where
camera rotation off-square alone biases knee flexion by up to 7.5°. Keep them as separate
series until an offset is measured on days where both exist.

**GPS is the exception** — Catapult both sides, same device. The only metric that pools
across training and match with no calibration work, which is why it is phase 1.

## What change is actually detectable

The viability answer, not an appendix:

| metric | per-ball σ | n/session | **detectable change** |
|---|---|---|---|
| front knee flexion | 6.1° | 25 | **3.5°** |
| trunk lean | 4.3° | 29 | **2.3°** |
| stride | 6.5 %ht | 27 | **3.5 %ht** |

Coarse but usable — a genuine shift in action, not subtle drift. **The free camera changes
in `CAMERA_OPTIONS.md` take the knee figure to 1.6°**, which is the cheapest sensitivity
available and reframes that work as a longitudinal investment.

⚠️ Ball speed and GPS noise floors are **not yet measured**. Run
`footageanalysis/biomech/noise_check.py` (or the same three lines) on them before
promising sensitivity.

## Where the identity crosswalk should live

Tom asked whether `referencebuilder` is the right home. **Recommendation: no —
`cricket-core`.**

- Every project needs to resolve a player; every project already imports `cricket-core`.
  `referencebuilder` is a *producer of derived cricket reference data* (norms, speed
  profiles), not an identity authority, and most projects do not depend on it.
- There is **no crosswalk module in cricket-core today** — checked. `headshots.resolve_name`
  resolves cricket.com.au ids only. So this is a genuine gap, not a relocation.
- The warehouse already has `*ExternalIds` views (type 40 = CricViz) and **scorecarddb
  owns a crosswalk it calls "the asset"**. A second, rival crosswalk is the failure mode
  to avoid — the new module should *wrap* those, not compete.

Suggested shape: `cricket_core.identity.resolve(...)` taking any of warehouse `player_id`,
Catapult athlete id, Cricket-21 id, CA id or a name, returning a canonical `player_id`.
Backed by a committed CSV now; **swap to Tom's reference table when the DB lands** — the
point of putting it behind a function is that the swap is invisible to callers.

**Radar has no player id at all.** sessionsync attributes deliveries to a bowler by GPS
run-up gate. So the training chain is radar ball → GPS athlete → canonical player, and the
GPS attribution is the weak link worth recording a confidence on.

## What exists to build on

The gap is a store and a report layer, **not a pipeline**:

| piece | where |
|---|---|
| Training ball speed + revs, GPS, biomech with uncertainty | sessionsync, done |
| Training vision + annotated frame rendering | sessionsync `clips/`, `qa_markers.py` `render()` |
| Match GPS per delivery, joined on `delivery_id` | `cricket_core.gps`, 141 matches |
| Match ball tracking (Hawkeye) | warehouse `Deliveries` |
| Match vision | `cricket_core.video` (Fairplay); Virtualeye 🔴 blocked on RBAC |
| Match biomech from Hawkeye footage | `footageanalysis/biomech` — see its `docs/FROM_SESSIONSYNC.md` first |
| Over-time multi-player comparison UI | `pages/career_progression.py` — the pattern, not the data |

## Phasing

- **P0** — sessionsync → store → one report. One player, training only. Cheap: every
  number including its uncertainty already exists. Deliverable: *"here are Bartlett's two
  sessions, here is the change, here is whether it is distinguishable from noise."*
- **P1** — **GPS across training and match.** The only valid cross-context metric today.
- **P2** — ball speed, once the radar↔Hawkeye offset is measured.
- **P3** — match biomech from Hawkeye. Highest value, highest risk of a phantom trend.
  Blocked on biomech's own noise question and the cross-calibration.
- **P4** — within-session trend (does knee flexion drift from ball 1 to ball 40). The
  per-ball table enables it; do not block on it.

## Traps, each already paid for elsewhere

1. **Do not store a value without its `se` and `n`.** Everything else follows from this.
2. **Do not plot two instruments on one axis** before measuring the offset.
3. **Do not report a change smaller than the detectable threshold** as a change. "No
   detectable change" is the honest and common answer.
4. **Do not let sessionsync own longitudinal state.** It is a session-review tool; it
   should emit to the store, not host it.
5. **Do not build a second identity crosswalk.** Wrap the warehouse views and scorecarddb's.
6. **Vision is a reference, not a blob.** Fairplay URLs are SAS-signed and expire — store
   identifiers, mint at read time via `cricket_core.video`. `briefings` has an expiry
   checker for the same reason.

## Open questions

1. **What counts as one "session" in a match?** Per-spell is the honest analogue — a
   bowler's action at ball 5 is not the same as ball 50. Per-match blurs it.
2. **Store: SQLite or straight to the DB Tom is getting access to?** SQLite is the
   suggestion for now (cricket21's mirror is precedent), but if the DB is imminent it may
   be worth waiting.
3. **How far back does this reconstruct?** catapultgps has 141 matches; the warehouse
   goes to ~2001. Biomech only exists forward from now. A player's "history" will be very
   uneven by metric, and reports need to say so rather than draw a line through gaps.
4. Where the ODI career tool lands — see `FUTURE_PROJECTS.md`.
