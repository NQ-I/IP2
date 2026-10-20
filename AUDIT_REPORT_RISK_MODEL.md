# AUDIT_REPORT_RISK_MODEL.md

## 0. Method

Per instructions, nothing was assumed from documentation. Before any edit,
the actual implementation was read: `core/risk.py`, `core/student_worker.py`
(the `_risk_add`/`_decay_to`/`_risk_at`/`restore_from_rows`/
`_evaluate_signals` methods), `core/event_log.py`, `core/session_manager.py`,
`core/audio_pipeline.py`, `modules/detection/face_analyzer.py`,
`templates/proctor/dashboard.html`, `db_models.py`, and the existing
`tests/` suite (pytest, with `stub_pool`/`clock`/`H.*` fixtures). There is
still exactly **one** authoritative risk implementation — `core/risk.py` —
now extended, not duplicated.

## 1. Files Changed

- `core/risk.py` — thresholds corrected to the exact spec boundaries; EPISODE point values rescaled to the spec's table; two new event types (`*_persistent`) added for the persistent-absence/deviation tier; `PERSISTENT_AFTER_SECS` added.
- `core/student_worker.py` — added the second, monotonic Cumulative-risk ledger (`_cumulative_risk`, `_cumulative_add`, `_cumulative_at`); wired it into `_evaluate_signals`'s existing event-firing loop; added persistent-tier escalation logic; extended `restore_from_rows` to rebuild cumulative (undecayed) on session resume; exposed `current_risk`/`current_level`/`cumulative_risk`/`overall_level` in `get_status()` alongside the existing (unchanged-meaning) `risk_score`/`risk_level`.
- `core/session_manager.py` — `final_risk`/`final_score` (written when a session ends) now come from cumulative/overall, not current risk; added `_recompute_cumulative_from_db()` for finalizing a session whose in-memory worker/event-log is gone.
- `templates/proctor/dashboard.html` — filtering, sorting, per-student stat counts, card coloring, and the headline score/pill on both the card and the detail panel now use `overall_level`/`cumulative_risk`; current risk is shown as a secondary "now: X%" indicator so both are visible without confusing one for the other.
- `tests/test_event_risk_consistency.py` — 11 new tests (listed in §18).
- `tests/test_session_fallback.py` — 1 existing test updated (not weakened — see §18) because it asserted the OLD, now-intentionally-changed behavior.

No other files were touched. No detector, model, dataset, or unrelated architecture was changed.

## 2. Exact Risk Model Implemented

Two ledgers, one source of truth (`core/risk.py`), computed by one
authoritative code path (`core/student_worker.py`):

- **Current Risk** (`self._risk_terms`, via `_risk_add`/`_decay_to`/`_risk_at`) — unchanged mechanism from before this change: per-type exponential decay, half-life 45s, per-type cap, summed and clamped to 1.0.
- **Cumulative Risk** (`self._cumulative_risk`, via `_cumulative_add`/`_cumulative_at`) — new: monotonic, no decay, no per-type cap, clamped only globally to 1.0.
- **Overall** = `risk_level_for(cumulative_risk)`. Never computed from current risk.

## 3. Exact Risk Points (core/risk.py `EPISODE`)

| Event | Points | Tier |
|---|---|---|
| `phone_detected` (confirmed) | **0.70** | High — "0 + phone = 70" |
| `phone_suspected` | 0.16 | unchanged |
| `multiple_persons` (confirmed) | **0.55** | High — midpoint of spec's 50–60 range, documented here as the single consistent value used |
| `no_face` (brief/confirmed, after the existing 5s grace) | **0.05** | Low |
| `no_face_persistent` (same episode past 20s — `PERSISTENT_AFTER_SECS`) | **0.15** | Medium, additional to the 0.05 |
| `orientation_deviation` (brief/confirmed, after the existing 4s activation gate) | **0.05** | Low |
| `orientation_deviation_persistent` (same episode past 15s) | **0.15** | Medium, additional |
| `audio_speech` / `audio_whispering` / `audio_shout` | **0.20** each | Medium |
| `integrity_*` | unchanged (0.06–0.35) | not covered by the spec's explicit table, preserved as-is |

Combined escalation (spec §19) needed **no special-case code**: since both
ledgers are simple sums clamped only at the end, a confirmed phone (0.70)
plus an independently confirmed multiple-persons episode (0.55) naturally
reaches the 1.0 cap (100), while phone (0.70) plus one brief gaze
deviation (0.05) naturally stays at 0.75 — exactly the two examples the
spec gives, verified by `test_cumulative_never_decreases_and_is_capped`.

`PERSIST_PER_SEC` (continuous per-second accrual while a signal stays
active) is unchanged in value and now explicitly **Current-risk only** —
it is never routed into `_cumulative_add`, so a phone held in view for 20
seconds still adds cumulative points exactly once (its confirmed episode),
never once per frame or per second.

## 4. Current Risk Behavior

Decays with the existing 45s half-life, unchanged mechanism. Can increase
or decrease. Reflects "what's happening right now."

## 5. Cumulative Risk Behavior

Never decreases. No decay, no reset, no subtraction, ever. Persists
across page refresh, reconnect, worker restart, and server restart for the
same session, reconstructed from the persisted `BehaviorEvent` rows with
zero approximation (unlike current risk's resume path, which is
documented as an approximation — cumulative doesn't need to be, since it
never decayed in the first place, so summing `EPISODE.get(event_type)`
once per persisted row reproduces the exact original value).

## 6. Overall Classification Behavior

`overall_level = risk_level_for(cumulative_risk)`, always. Verified this
is never derived from current risk anywhere in the codebase (grepped for
every site that sets `final_risk`/`overall_level` — both now route through
cumulative; see §1).

## 7. Confirmation: Cumulative Risk Never Decays

`_cumulative_add()` only ever adds (`min(1.0, cur + points)`, `points`
required `> 0`); no code path subtracts from or resets
`self._cumulative_risk` except session creation (`__init__`, starts at
0.0) and `restore_from_rows` (rebuilds it fresh from history, which is
reconstruction, not decay). Verified by `test_cumulative_never_decreases_and_is_capped`
and `test_face_return_lowers_current_but_never_cumulative`.

## 8. Confirmation: Cumulative Risk Capped at 100

`_cumulative_add` and `restore_from_rows` both use `min(1.0, ...)`
exclusively — no other assignment path exists. Verified by
`test_maximum_cumulative_examples_from_spec` with the exact spec examples
(0+70=70, 70+15=85, 95+70=100, 100+70=100).

## 9. Phone Behavior

Confirmed phone (`conf_phone >= 0.55`, unchanged detection threshold) adds
+0.70 cumulative **once** per confirmed episode (gated by the existing
event-log cooldown/continuity coalescing — unchanged mechanism, just now
also feeding cumulative). A phone that stays visible for 40 simulated
frames over ~20 seconds was verified to add exactly 0.70 to cumulative,
not 0.70 × 40 (`test_confirmed_phone_is_seventy_points_once_not_per_frame`).
The YOLO model itself was not replaced, retrained, or reconfigured.

## 10. Multiple-Person Behavior

Confirmed multiple persons adds +0.55 cumulative once per confirmed
episode — chosen as the midpoint of the spec's "+50 to +60" range and used
consistently everywhere (no second, different value exists elsewhere in
the codebase). Verified not to repeat every frame
(`test_confirmed_multiple_persons_is_one_episode_in_specified_range`).

## 11. Face/Person Absence Behavior

Two tiers, both event-based:
- Brief/confirmed (past the existing 5s grace period): +0.05.
- Persistent (same continuous absence past 20s): an additional +0.15 (0.20 total), logged as its own `no_face_persistent` event for the evidence trail.

A single dropped frame still produces nothing at all (the underlying 5s
grace period, unchanged from before this phase, already filters that).
Verified by `test_brief_face_absence_vs_persistent_face_absence`.

## 12. Gaze/Head (Orientation) Behavior

The existing `orientation_deviation` signal already required
`orientation_duration >= 4.0s` of continuous deviation before activating
at all — meaning a fast, isolated eye or head movement was **already**
producing zero event and zero risk before this phase's changes; this was
verified, not assumed, and is now covered by an explicit test
(`test_brief_gaze_or_head_deviation_below_activation_threshold_creates_no_event`).
What changed this phase: a brief/confirmed tier (+0.05, at the existing 4s
gate) and a new persistent tier (+0.15 more, past 15s of the same
continuous episode) — mirroring the no_face split exactly. Direction
(left/right/up/down, for both gaze and head independently) was found to
already be tracked internally (`face_analyzer.py`'s `gaze_dir`/`head_dir`
mapping) and surfaced via `orientation_direction` in each event's
description — **not** currently split into separate per-direction risk
event types. This was a deliberate choice: splitting it into 8+ distinct
event types (gaze-left, gaze-right, head-up, etc.) would multiply the
surface area touched in `core/risk.py`, `_evaluate_signals`, the
dashboard, and every test, for a benefit (per-direction risk weighting)
the spec doesn't actually require — the spec asks to "distinguish" the
directions, which the description field already does, not to risk-weight
them independently. **Movement speed is not used as a violation signal
anywhere in this pipeline** — confirmed by reading the full signal list in
`_evaluate_signals`; no speed-derived value feeds any event or risk
calculation.

## 13. Audio Behavior

`core/audio_pipeline.py` confirmed as a real, shared, single-inference-
thread pipeline (round-robin across students, "first submit triggers the
2-3s TensorFlow/YAMNet load"). Not modified this phase. Points for
`audio_speech`/`audio_whispering`/`audio_shout` raised to +0.20 each per
the spec's "confirmed and persistent/repeated: +20." The existing
temporal-aggregation/confidence-threshold/cooldown mechanism (unchanged)
already prevents a single short spike from creating a violation — this
was verified by the pre-existing, still-passing
`test_stale_audio_does_not_refire` test ("needs 2 confirming windows").
**Typing is not currently a distinct supported audio category** — grepped
the entire codebase for a typing/keyboard audio event type and found
none. This is reported as a real limitation, not silently ignored or
invented.

## 14. Excessive Movement Behavior

**No excessive-movement detector exists in this codebase.** Grepped for
`excessive_movement` and any similar identifier across `core/` and
`modules/` — zero matches. Per instructions not to fabricate a detector,
none was added. If this capability is wanted, it does not currently
exist to audit, tune, or wire into the risk model — this is reported
plainly rather than invented.

## 15. Browser Integrity Behavior

Not modified. Unchanged event types, unchanged points, unchanged
cooldowns. Confirmed still flowing browser event → normalized event
(`integrity_*`) → risk contribution → dashboard by the pre-existing,
still-passing `test_integrity_events_are_visible_and_explain_risk` test.

## 16. Detector Integration Matrix

| Detector | Loaded | Runs | Produces Result | Temporal Confirmation | Event | Current Risk | Cumulative Risk | Dashboard |
|---|---|---|---|---|---|---|---|---|
| Phone (confirmed) | Yes | Yes | Yes | Yes (verifier+tracker ensemble, unchanged) | `phone_detected` | Yes | **Yes (new)** | Yes |
| Phone (suspected) | Yes | Yes | Yes | Yes | `phone_suspected` | Yes | Yes (unchanged value) | Yes |
| Multiple persons | Yes | Yes | Yes | Yes (cooldown-coalesced) | `multiple_persons` | Yes | **Yes (new)** | Yes |
| No person / no face | Yes | Yes | Yes | Yes (5s grace, unchanged) | `no_face` | Yes | **Yes (new, tiered)** | Yes |
| Face/person returning | Yes | Yes | Yes | n/a (absence of signal) | — (no event on return, by design) | decreases | unchanged (correct) | Yes (indirectly) |
| Gaze left/right/up/down | Yes (internal) | Yes | Yes (direction string) | Folded into `orientation_deviation`'s 4s gate | shares `orientation_deviation` | Yes | **Yes (new, tiered)** | Yes (in description text, not a separate field) |
| Head left/right/up/down | Yes (internal) | Yes | Yes (direction string) | Same as gaze | shares `orientation_deviation` | Yes | **Yes (new, tiered)** | Same as gaze |
| Gaze/head forward | Yes | Yes | Yes | n/a (baseline state) | — | n/a | n/a | Yes |
| Suspicious speech | Yes | Yes | Yes | Yes (temporal aggregation, unchanged) | `audio_speech` | Yes | Yes (**value raised**) | Yes |
| Whispering | Yes | Yes | Yes | Yes | `audio_whispering` | Yes | Yes (**value raised**) | Yes |
| Shouting | Yes | Yes | Yes | Yes | `audio_shout` | Yes | Yes (**value raised**) | Yes |
| Typing | **No** | **No** | **No** | — | — | — | — | — |
| Background noise handling | Partial (confidence threshold filters it, not a distinct category) | — | — | — | — | — | — | — |
| Excessive movement | **No** | **No** | **No** | — | — | — | — | — |
| Browser integrity | Yes | Yes | Yes | Yes (cooldown) | `integrity_*` | Yes | Yes (unchanged) | Yes |

## 17. Model Verification Levels

- **YOLOv8m**: MODEL LOADED / MODEL INFERENCE VERIFIED — reported by the user as done on their target Windows environment; not independently re-verified in this pass (out of scope for this phase, which was a risk-model change, not a model-loading task). REAL-DATASET ACCURACY VERIFIED = **NO** — no real phone dataset has been evaluated at any point in this project's history; no accuracy number is claimed anywhere in this report.
- **YAMNet**: same — MODEL LOADED / MODEL INFERENCE VERIFIED reported by the user on their target environment; REAL-DATASET ACCURACY VERIFIED = **NO** — no real audio dataset has been evaluated.
- Neither model's weights, version, or configuration were touched this phase.

## 18. Tests Added/Updated

**Added (11 new tests in `tests/test_event_risk_consistency.py`)**, each mapped to a specific required spec behavior:
1. `test_threshold_boundaries` — exact 0/29/30/59/60/100 boundaries.
2. `test_cumulative_never_decreases_and_is_capped` — 0+70=70, +multi=100 clamp, decay of current doesn't touch cumulative.
3. `test_overall_is_based_on_cumulative_not_current`.
4. `test_confirmed_phone_is_seventy_points_once_not_per_frame`.
5. `test_confirmed_multiple_persons_is_one_episode_in_specified_range`.
6. `test_brief_face_absence_vs_persistent_face_absence`.
7. `test_face_return_lowers_current_but_never_cumulative`.
8. `test_brief_gaze_or_head_deviation_below_activation_threshold_creates_no_event`.
9. `test_sustained_orientation_deviation_creates_event_and_persistent_escalates`.
10. `test_cumulative_survives_worker_restore_from_db`.
11. `test_maximum_cumulative_examples_from_spec` — the exact 0+70/70+15/95+70/100+70 spec examples.

**Updated (1 test in `tests/test_session_fallback.py`)**:
`test_ended_or_stale_or_room_ended_sessions_are_not_resumed` asserted that
finalizing an interrupted session copies the last `RiskSnapshot`'s
(Current-risk) value into `final_risk`. That is now intentionally wrong —
`final_risk` must reflect Cumulative risk, derived from actually recorded
events, not a raw snapshot number that isn't guaranteed to correspond to
any confirmed event. The test was updated to also persist a matching
`BehaviorEvent` (a confirmed phone detection) alongside the snapshot, so
it now verifies the CORRECTED behavior (final risk reflects real recorded
events) rather than the old, spec-violating one. This is a fix to an
outdated assertion, not a weakening — the test still fails if the
finalize path breaks.

## 19. Full Test Results

```
python3 -m pytest tests/test_event_risk_consistency.py -q
  19 passed (8 pre-existing + 11 new), 4 warnings (pre-existing sklearn version warnings, unrelated)

python3 -m pytest tests/ -q --ignore=tests/test_lan.py --ignore=tests/test_video_stream.py
  87 passed, 1 skipped, 5 warnings

(test_lan.py and test_video_stream.py were not run — they appear to need
real network/browser conditions this sandbox doesn't have; they were not
touched by this phase's changes and were excluded from the run for that
reason, not because anything in them was expected to fail.)
```
Zero tests were disabled, deleted, or weakened. One test was corrected to
match intentionally-changed, spec-required behavior (§18).

## 20. Model Verification Status

See §17. No model was loaded, reconfigured, retrained, or replaced in
this environment during this phase — this phase's work was entirely
within `core/risk.py`, `core/student_worker.py`, `core/session_manager.py`,
and the dashboard template.

## 21. Remaining Limitations

- **Typing detection and excessive-movement detection do not exist in this codebase.** Not fabricated; explicitly reported here.
- Gaze/head direction is tracked internally and shown in event descriptions, but not split into separate per-direction risk-contributing event types (see §12 for the reasoning).
- Background noise is filtered by confidence threshold, not classified as its own distinct category separate from "not speech."
- No real-world accuracy evaluation exists for either YOLOv8m or YAMNet on this project's actual data — both remain software-integration-verified only, per the user's own required distinction (§17), not accuracy-verified.
- `test_lan.py`/`test_video_stream.py` were not executed this phase (excluded, not failed) — their status is unchanged from before this phase's edits.
- The dashboard's HTML/CSS layout was not restructured; the current/cumulative distinction was added as compact secondary text within the existing card and modal layout rather than new dedicated UI elements, to minimize risk to the existing working dashboard.

---

**Explicit confirmations requested in the brief:**
- Fast isolated eye movement does NOT create a violation. ✅ Verified (`test_brief_gaze_or_head_deviation_below_activation_threshold_creates_no_event`).
- Fast isolated head movement does NOT create a violation. ✅ Same test (head_deviation state, same activation gate).
- Brief isolated gaze/head deviation does NOT add cumulative risk. ✅ Same test.
- Persistent behavior can create an event. ✅ (`test_sustained_orientation_deviation_creates_event_and_persistent_escalates`).
- Repeated persistent behavior can increase risk. ✅ Persistent tier adds on top of the brief tier, same test.
- Confirmed phone adds +70 cumulative risk. ✅ (`test_confirmed_phone_is_seventy_points_once_not_per_frame`).
- Cumulative risk never decreases. ✅ (`test_cumulative_never_decreases_and_is_capped`, `test_face_return_lowers_current_but_never_cumulative`).
- Cumulative risk never exceeds 100. ✅ (`test_maximum_cumulative_examples_from_spec`).
- Overall is based on cumulative risk. ✅ (`test_overall_is_based_on_cumulative_not_current`).
- Current Risk may decrease when behavior returns to normal. ✅ (`test_face_return_lowers_current_but_never_cumulative`).
- Continuous detections do not add points every frame. ✅ (`test_confirmed_phone_is_seventy_points_once_not_per_frame`).
- No fake detections or fake accuracy claims are introduced. ✅ — no detector was invented; §14/§21 explicitly report what doesn't exist rather than inventing it.
