# Tracking a player's physical and technical profile over time

*Proposal, 2026-08-05. Written from the sessionsync side after measuring what these
metrics are actually worth. Nothing here is built yet — this is the approach and the
decisions it needs.*

## What's wanted

Run a session, put the numbers in a store, keep screenshots and vision links, and
generate reports that answer: **is their speed changing? are they getting more knee
flexion? what is their run-up speed doing?** Then the same off match data, where ball
speed, GPS and Hawkeye vision all line up.

## Most of the pieces already exist

The gap is a **store and a report layer**, not a pipeline. Inventory:

| piece | where | state |
|---|---|---|
| Training ball speed + revs | sessionsync ← Stalker radar | done |
| Training GPS (run-up speed, load, peak power) | sessionsync ← Catapult | done |
| Training biomech (knee, stride, trunk) | `sessionsync/scripts/biomech_metrics.py` | done, with uncertainty |
| Training clips per delivery | sessionsync `clips/` | done |
| Annotated frame rendering | `sessionsync/scripts/qa_markers.py` `render()`, `biomech/release_shots.py` | done |
| **Match** ball tracking (Hawkeye) | warehouse `Deliveries` | done |
| **Match** GPS, per-delivery, joined on `delivery_id` | catapultgps → `cricket_core.gps` | done, 141 matches |
| **Match** vision | `cricket_core.video` (Fairplay); Virtualeye 🔴 blocked on RBAC | partial |
| **Match** biomech from Hawkeye footage | `footageanalysis/biomech` | works for one bowler |
| Over-time comparison UI | `playertracker/pages/career_progression.py` | done, wrong data |

## Two constraints that have to shape the design

### 1. The reportable unit is a session, not a delivery

Measured on 4 Aug across 32 deliveries: **80–100 % of the ball-to-ball spread in these
metrics is measurement noise, not the bowler.** A single delivery's knee flexion is worth
±6.1° against real ball-to-ball variation of 2.9°. Two balls reading 40° and 64° are not
doing different things.

The session median is sound — noise falls by √n — but it means:

- **Every stored value carries its standard error and its n.** Not optional, not a
  display detail. A store that keeps bare numbers will produce confident-looking charts
  of nothing.
- Per-ball rows are still worth keeping (drill-down, re-aggregation, within-session
  trend), but they are **not** the reporting grain.

### 2. Instrument is part of the series identity

The trap that would quietly wreck this: **training and match measure the same quantity
with different instruments, and the difference will look like the player changing.**

- Ball speed: Stalker radar (training) vs Hawkeye (match). Different devices, almost
  certainly a systematic offset.
- Biomech: a wide training camera (bowler 393 px tall, 6 Mbps) vs Hawkeye broadcast.
  Different noise *and* different bias — camera rotation off-square biases knee flexion
  by up to 7.5° (measured, `sessionsync/docs/CAMERA_OPTIONS.md`).
- **GPS is the exception** — Catapult both sides, same device, same firmware. It is the
  one metric that can be pooled across training and match with no calibration work.

So: `knee_flexion@sessionsync-sideon` and `knee_flexion@hawkeye` are **different series**.
They can be joined only through a measured offset, established on days where both exist.
Until that offset is measured, a report must not plot them on one axis.

## What change could you actually detect?

This determines whether the product is worth building, so it goes near the top rather
than in an appendix. From the measured per-ball noise:

| metric | per-ball σ | n/session | session SE | **detectable change** |
|---|---|---|---|---|
| front knee flexion | 6.1° | 25 | ±1.22° | **3.5°** |
| trunk lean | 4.3° | 29 | ±0.80° | **2.3°** |
| stride | 6.5 %ht | 27 | ±1.25 | **3.5 %ht** |

(detectable ≈ 2 × σ√(2/n), i.e. a change you'd call real at ~95 % between two sessions)

**Verdict: usable but coarse.** A 3.5° knee change is bigger than Bartlett's own
ball-to-ball variation, so you can catch a genuine shift in action — you cannot catch
subtle drift.

Two things sharpen it, and both are already on the table:

**More balls per session** — √n, so it is slow going:

| balls | detectable knee change |
|---|---|
| 25 | 3.5° |
| 50 | 2.4° |
| 100 | 1.7° |

**Better capture** — this is the big one, and it reframes the camera work as a
*longitudinal* investment rather than a cosmetic one:

| capture | per-ball σ | detectable change (n=25) |
|---|---|---|
| now — 36 % of frame, 6 Mbps, slow shutter | 6.1° | 3.5° |
| **zoom to 80 % of frame** (free) | 2.8° | **1.6°** |
| zoom + fast shutter + 100 Mbps (est.) | 2.2° | 1.2° |
| 4K + reframed | 1.4° | 0.8° |

**The free camera changes more than halve the change you can detect.** If longitudinal
tracking is the goal, they stop being nice-to-have.

⚠️ Ball speed and GPS have their own noise floors, not yet measured. Radar speed is
probably far tighter than pose; run-up speed unknown. Same three-line test applies
(`biomech/noise_check.py`) and should be run before promising sensitivity on those.

## Where it should live: repurpose `playertracker`

**Recommendation, and it needs your call.** playertracker currently builds ODI career
progression — one row per player per match, comparing career trajectories. That job is
being absorbed by **scorecarddb**, whose stated purpose is *"reach back before the
ball-by-ball era — full career records"*. Two projects computing career aggregates is one
too many.

That leaves playertracker with the right name, a Streamlit multi-player over-time
comparison UI that is directly the shape wanted, and no remaining unique job.

- **For:** name fits, UI pattern reusable, avoids a fifteenth repo, retires a duplicate.
- **Against:** the existing career pages would be deleted or moved to scorecarddb; if the
  ODI career tool is still used by anyone, that is a real cost.
- **Alternative:** new project (`playerprofile` is taken; something like `athleteprofile`).
  Cleaner separation, more setup, another repo on the estate.

**Not sessionsync.** It is a session-review tool; giving it longitudinal state across
players and sources would muddle a thing that currently does one job well. It should
*emit* to the store, not own it.

## Data model

Three tables. SQLite to start — local, no infrastructure, and the cricket21 mirror is
precedent for it on this estate.

```
observation      the reporting grain: one player, one date, one metric, one instrument
  player_id, date, context (training|match), source_id (session or match+innings)
  metric, value, se, n, quality
  instrument            <-- part of the series identity, never dropped
  
delivery         per-ball raw, for drill-down / re-aggregation / within-session trend
  player_id, source_id, ball_no, epoch, metric, value, quality_flags
  
evidence         screenshots and vision, hung off an observation or a delivery
  ref, kind (clip|frame|marker), url_or_path, caption
```

Notes that matter:

- `se` and `n` are **required** on `observation`. A row without them cannot be charted.
- `instrument` distinguishes `stalker-radar` from `hawkeye`, `sessionsync-sideon` from
  `hawkeye-endon`. Reports group by it until an offset is measured.
- `quality` carries through the per-metric gating sessionsync already does — a flagged
  measurement is stored and visible, not silently dropped.
- Vision is stored as a **reference, not a blob**. Fairplay URLs are SAS-signed and
  expire; the store keeps the identifiers and mints a URL at read time via
  `cricket_core.video`. (Same reason `briefings` has an expiry checker.)

## Phasing

**P0 — prove the loop on what already works.** sessionsync → store → one report.
One player, training only, the metrics that exist. Deliverable: "here are Bartlett's two
sessions, here is the change, here is whether it's distinguishable from noise." Cheap,
because sessionsync already produces every number including its uncertainty.

**P1 — GPS across training *and* match.** The only cross-context metric that is valid
today, because Catapult is the same instrument both sides. `cricket_core.gps` already
reads 141 matches. This gives real longitudinal reach — run-up speed and workload over a
season — without waiting on any calibration.

**P2 — ball speed, once the radar↔Hawkeye offset is measured.** Needs days where a player
appears in both close together. Until then, two series.

**P3 — match biomech from Hawkeye footage.** Depends on `footageanalysis/biomech`, and on
two things settled first: its own noise question (`biomech/noise_check.py`, see
`biomech/docs/FROM_SESSIONSYNC.md`), and the cross-calibration against training. Highest
value and highest risk of a phantom trend if rushed.

**P4 — within-session trend.** The per-ball table enables "does his knee flexion change
from ball 1 to ball 40" — fatigue within a session. Worth having, not worth blocking on.

## Open questions

1. **Repurpose playertracker, or a new project?** The one decision that blocks starting.
2. **Who reads the reports** — coach, S&C, physio, selector? Drives whether the unit is
   "this session vs last" or "this season vs last".
3. **Player identity across systems.** Warehouse `player_id`, Catapult athlete id, and
   radar (which has none — sessionsync attributes by GPS). A crosswalk probably exists in
   pieces; needs confirming before the store is keyed.
4. **What counts as one "session" in a match?** Per-spell is the honest analogue of a
   training session — a bowler's action at ball 5 of a spell is not the same as ball 50.
   Per-match would blur that.
5. **Is the ODI career tool still used?** Decides whether repurposing costs anything.
