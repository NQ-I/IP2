# Phase 4: gaze reliability, a separate Behavioral State, dataset / training preparation

This phase covers three things.

1. **Gaze.** The audit used your own 172 s recording (replayed through the real analyzer at the
   production rate of 3 analysed frames per second), your screenshots and real photos.
   The fix is minimal and **no threshold was changed**.
2. **Behavioral State.** A new, completely separate module ("Calm / Anxious / Model not
   trained") for the proctor. It never touches the cheating risk.
3. **Preparation only.** Dataset folders, schemas, validators and training / evaluation
   scripts. **Nothing was trained, generated or downloaded as data.**

Your recording, the frames cut from it and your screenshots were used locally for analysis.
They are not part of the delivery.

Status words: **PASS**, **PARTIAL**, **NOT VERIFIED**. Nothing is marked as passed without a
measurement or a test.

---

## Part 1: Gaze

### 1. Root cause

The replay was done with the unchanged analyzer at 3 Hz. Frames counted: head centred, eyes
open, calibrated.

**16.8 % of them had a gaze confidence just under 0.60** (32 of 190 frames). The gaze was then
"not measurable". Causes:

- dim light: face brightness 56–65 gives image quality 0.70 and a confidence of about 0.57;
- one eye mis-tracked: the two eyes disagree;
- a saccade: a jump between two frames.

These frames come in short runs: 15 of 17 runs last 0.33–1.0 s.

Each such frame did two things in the old code:

1. The gaze label was **reset to "Looking Center"**. The direction then needed its 0.35 s
   confirmation again: three more measurable frames.
2. The eyes-only episode turned into **"normal"**, because the head was valid but had no
   direction. **The 4-second timer restarted.**

So an eyes-only look held for 4 s survived without a reset only about **11 %** of the time
(0.832¹² = 0.11).

**Fix** (`modules/detection/face_analyzer.py`). A frame whose gaze is not measurable is "no
information about the eyes", the way a blink already was:

- The direction is kept for up to 2.0 s. This is the existing `ORIENTATION_INVALID_TOLERANCE`;
  no new constant was added.
- The orientation reports `unknown` for that frame. An `unknown` frame never creates or
  extends an event on its own.
- The first measurable frame decides:
  - eyes still away → the episode continues;
  - eyes back → it ends **at once**. This last rule came out of the independent review: without
    it, a 3.3 s look plus 1.7 s of unmeasurable frames became a 4.3 s violation. There is now a
    test for that case.

Measured on real photos, at 3 Hz, holding a look to the right for 6 s with every 4th frame dim:

| | Before | After |
|---|---|---|
| Gaze label | flips Right / Center | Right |
| Orientation | never left "normal" (max 0.67 s) | `eye_deviation` right, 4.33 s → event |

**Other root causes measured, not changed** (each needs a threshold change the data does not justify):

- **Calibration.** On your recording, strict calibration never completed, for two reasons:
  - 10 head-step resets in the first 25 s;
  - your reading pitch drifted 0 → −10°, beyond the 4° stability test.

  The mode-seeking fallback calibrated at 45 s, so **head / gaze detection starts at up to 45 s**
  when the head moves at the start.
  - **Experiment:** "skip instead of reset". Still no strict calibration (the spread test failed), so it was not adopted.
  - **Fallback neutral:** this neutral is your reading posture (eyeLookDown 0.51, eyeBlink 0.43). The reading posture is therefore absorbed.
- **Head down + eyes up.** Your head-down episode at 122.8–131.1 s (pitch −11…−14°) had
  eyeLookUp 0.19–0.22. That is just below the eyes-up threshold of +0.22, so the system could
  not recognise "eyes up = still looking at the screen". It stayed a **Head Down** event.
  Head detection was not changed (out of scope). Reported here as an observation.

### 2. Left

**Status:** PASS on real media. PARTIAL for your moderate glance.

- **Real photos.** `face_img4` (looking to her left) → **Looking Left**, with a ≥ 4 s
  `eye_deviation` (test).
- **Mirror check.** A mirrored frame turns the same look into **Looking Right** (test). The
  decision follows the raw camera frame, from the **student's** point of view.
- **Your 134.5–137.8 s glance** (head turned +7° to the right):
  - iris +0.04…+0.08, i.e. **0.56–1.04 × the threshold**;
  - classified **Center**.
- **Why the threshold stays.** 0.08 is about 11–12° of eye rotation. A smaller value would flag
  eyes that **counter-rotate** to keep reading while the head is slightly turned.
  - Measured on your reading frames, the eyeLookIn/Out blendshape follows head yaw (**r = 0.72**,
    +0.016 per degree). The iris position does not (**r = 0.12**).
  - This is also why blendshapes were **rejected** for left / right (see 7).

### 3. Right

**Status:** PASS, with your own head-centred frames.

- **Your own glance.** 22.45–23.92 s of your recording: head yaw +0.1…+0.6°, pitch +0.4…+1.0°.
  - Per-eye iris x 0.27–0.29 and 0.33–0.38 (neutral 0.495).
  - eyeLookIn/Out 0.58–0.72.
- **Replay after calibration:**
  - **Looking Right** from 23.18 s;
  - exceedance **2.2–2.3 ×** the threshold;
  - the first frame of the saccade was unmeasurable (jump factor 0.67).
  - The glance lasted about 1.5 s, so **no event**, which is correct.

  In the original live run this glance happened **during calibration** (before 45 s), so nothing was shown then.
- **Real photo.** `face_img1` → **Looking Right**, ≥ 4 s `eye_deviation` (test).

### 4. Up

**Status:** PARTIAL. **NOT VERIFIED** for a pure upward look on your hardware.

- **Your "eyes up" screenshot (u1)** was up **and** to your right:
  - eyeLookUp 0.36 against neutral 0.01 → **1.58 ×**;
  - iris x 0.332 → Right **2.0 ×**.
- **Label.** Right, the larger normalised exceedance. The diagnostics now state:
  `U above threshold (1.57 x) but Looking Right is larger`.
- **Pure up with your measured values** → **Looking Up** (test). Up is reachable on its own.
- **Your reading frames** have eyeLookUp ≤ 0.08 → Center (test).
- There is no head-centred, pure "eyes up" clip of you.

### 5. Down

**Status:** PASS for "blink is not Down". **NOT VERIFIED** for an eyes-only lap look by you.

- **Your neutral.** eyeLookDown is **0.51**: the camera is above the screen, so reading already
  looks down. "Down" therefore needs ≥ **0.81**.
- **Your blinks.** eyeBlink 0.58–0.65, eyeLookDown 0.62–0.72 → **Eyes Closed** (single frames),
  never Down. Correct.
- **Real GIF frames.** Lowered eyes held for more than 1 s with eyeLookDown 0.82–0.91 →
  **Looking Down**, back-dated (existing test, still passing).
- **Not lowered.** Your own closed eyes reach 0.72 on eyeLookDown, so lowering the +0.30 margin
  would turn long blinks into "Down".
- **Consequence.** A lap look that leaves eyeLookDown below 0.81 shows as "Eyes Closed" and gives
  no Down event. This needs a recording of you looking at the lap (`tools/live_diag.py`, step 9).

### 6. Threshold / calibration changes

**None.** The values are unchanged:

| Setting | Value |
|---|---|
| Side | 0.08 |
| Up | +0.22 (blendshape) |
| Down | +0.30 |
| Blink | ≥ max(0.55, neutral + 0.20) |
| Lowered eyes | after 1.0 s |
| Minimum confidence | 0.60 |
| Dwell | 0.35 s |
| Exit | 0.65 × threshold |
| Calibration | unchanged |

**Added:**

- **The hold:** ≤ 2.0 s, the existing constant.
- **Immediate end** when the first measurable frame is back.
- **Gaze diagnostics `gaze_debug`** in every analysis, in the `PROCTOR_DIAG=1` line and in the
  `tools/live_diag.py` report:
  - raw per-eye iris values and blendshapes;
  - neutral values;
  - relative values;
  - each direction's threshold and normalised exceedance;
  - the selected direction and the rule;
  - why every other direction lost;
  - the confidence factors and the reason a frame was not valid.

### 7. False-positive checks

- **Full replay of your recording, before vs after:**
  - **identical** ≥ 4 s episodes: Head Right 98.4–100.0 s, Head Down 122.8–131.1 s, Head Down 153.7–154.4 s;
  - **zero** eyes-only episodes;
  - identical label counts (Center 223, Unknown 124, Eyes Closed 2).
- **Reading frames** (iris 0.45–0.53, eyeLookDown up to 0.72) → Center (test).
- **Limits of the hold** (tests):
  - longer than 2 s with no measurable gaze → the look ends, no violation;
  - eyes back during the unmeasurable frames → ends on the first measurable frame, no violation.
- **Rejected after measurement:** eyeLookIn/Out for left / right. It follows head yaw (r = 0.72),
  so a student reading with a slightly turned head would become "Looking Left/Right".

---

## Part 2: Behavioral State (restlessness / anxiety-like behaviour)

### 8. Architecture

The code is the package `modules/behavior/`:

| File | Role |
|---|---|
| `schema.py` | Features, labels, windows. One definition for live, recorder, training and validator. |
| `motion.py` | Body / hand motion energy. |
| `hands.py` | MediaPipe HandLandmarker, shared, thread-safe, optional. |
| `features.py` | Per-student feature tracker + temporal aggregation. |
| `classifier.py` | `AnxietyBehaviorClassifier`. |
| `monitor.py` | Per-student `BehaviorMonitor`. |
| `offline.py` | The same pipeline over a video. |

```
face path (3 Hz) ── newest frame per student (latest wins) ──► behaviour thread (own, single)
                                                               ├─ motion energy (every sample)
                                                               ├─ hand landmarks (only when due, see 11)
                                                               ├─ features 15 s / 60 s / session
                                                               └─ every 5 s: classifier → state
proctor status / dashboard ◄── behavior_state (label + counts, no %)
exam_sessions.behavior_summary ◄── every 60 s + at submit / logout → report section
```

**Isolation from detection.** The behaviour work runs on its **own thread**. Measured: inside the
single face thread it had cut the head / gaze rate of 10 students from 2.9 to 2.0 fps.

| Safeguard | Setting |
|---|---|
| Duty-cycle cap | `BEHAVIOR_MAX_CPU`, default 0.1 of one core |
| Hands skipped | while the head / gaze thread has students waiting |
| Errors | swallowed |
| Module off | `BEHAVIOR_ANALYSIS=0` |
| Hands off | `BEHAVIOR_HANDS=0` |

**States** (the classifier abstains instead of guessing):

| Display | When |
|---|---|
| **Model not trained** | default: no model installed |
| Calm / Anxious / Uncertain | with a trained model |
| **Not enough data** | < 30 s, face < 50 %, sampling < 90 frames/min, or hand features not measured while the model uses them |

`ANXIETY_DEV_HEURISTIC=1` is a **development** rule (two or more strong cues). It is labelled
"(dev heuristic)" everywhere and is off by default.

### 9. Features implemented

There are 22 per window (`feature_schema.json`).

**Sampling quality.** These are not model inputs; the classifier uses them to abstain.

- `coverage_s`
- `face_visible_frac`
- `analysed_per_min`
- `hand_analysed_per_min`

**Behaviour:**

- **Motion:** `motion_mean`, `motion_p90`, `excess_motion_frac`, `fidget_per_min`
- **Head:** `head_speed_mean`, `head_speed_p90`, `rapid_head_per_min`, `head_reversals_per_min`
- **Gaze:** `gaze_changes_per_min`, `iris_speed_mean`
- **Posture:** `posture_shifts_per_min`, `rocking_score`, `rocking_amplitude`
- **Hands:**
  - `hand_visible_frac`
  - `face_touch_per_min`, `face_touch_frac`
  - `hand_near_mouth_frac`
  - `nail_biting_candidates_per_min`

### 10. Features rejected

| Feature | Why |
|---|---|
| Tremor (4–12 Hz) | Not measurable at a 1–3 Hz analysis rate. |
| Blink rate | Blinks last 0.1–0.4 s; most are missed at 3 Hz. |
| Body pose | MediaPipe PoseLandmarker could not be built from the available model files here; frame-difference motion is used instead. |
| Facial emotion | No validated model, and it would be a diagnosis-like claim. |
| rPPG heart rate | Unreliable on 320×240 JPEG, and it is health data. |
| The old `face_touch_freq` | A "nose below 78 %" proxy. It is no longer used as a face touch. |
| eyeLookIn/Out for gaze | See 7. |

### 11. Face-touch implementation

- **Hand landmarks.** Real MediaPipe HandLandmarker, 21 landmarks per hand, up to 2 hands.
  - Model: `models/hand_landmarker.task`; source and SHA-256 in `models/HAND_LANDMARKER_SOURCE.md`;
  - `tools/fetch_behavior_models.py` can re-create it.
- **Touch.** At least 2 hand landmarks inside the face box (+10 % sides, +15 % up, +10 % down).
- **Face hidden by the hand.** The last face geometry is kept for 2 s, because the hand often hides the face.
- **Episode end.** An episode ends after 2 checks in a row without a touch (hysteresis). Without
  it, one phone held at your face counted twice.

**When the hands are checked** (cost, see 25):

- when something moves around the face (≥ 1.5 s apart);
- every 3rd sample while a hand is at the face;
- otherwise every 9th sample (~3 s).

**Measured on real images:**

| Image | Result |
|---|---|
| COCO 395 (hand + phone at the face) | **touch** |
| face_img59, face_img37 (hands below the face) | **no touch**, mouth distance > 0.35 face widths |
| face_img10 | no hand |

**Your recording:**

- **Detected:** two touch episodes.
  - 67.5 s: a hand over the forehead / head.
  - 81.7 s: a phone held at the face. One episode with the hysteresis.
- **Correctly not touches:** hands raised beside the head at 66–67 s.
- **Missed:** a brief, motion-blurred hand over the face at about 58 s, between checks.

**Limits.**

- A 2-D overlap is not physical contact.
- Touches shorter than about 1.5 s can be missed.

### 12. Nail-biting status

Only **`possible_nail_biting` candidates**: a fingertip within 0.20 face widths of the mouth
centre for **≥ 2 s**.

- It is never shown as a fact.
- No accuracy is claimed and there is no data.

Unit-tested:

- 1 brief contact → 0 candidates;
- held → 1 candidate;
- hand on the desk → 0.

### 13. Excessive movement

The measure is the fraction of changed pixels **outside the head region**. Compensations:

| Compensation | How |
|---|---|
| Head region excluded | Face box ±40 %, +50 % up for the hair, +30 % for the neck. |
| Camera jitter | Removed by phase correlation, only when that alignment explains the change (≥ 30 % fewer changed pixels). |
| Exposure change | The median difference is subtracted. |
| Noise | Threshold of 12 grey levels. |

Excessive = above 3 × **the student's own** noise floor (20th percentile of the last ~60 s),
minimum 0.02.

- **Your recording:** still periods 0.006–0.02; your test movements 0.1–0.4.
- **Bug found and fixed on real data:** this OpenCV build modifies the inputs of
  `phaseCorrelate` in place. It had produced 42 % "motion" on a still scene.

### 14. Rapid movement

- **Head speed:** pitch + yaw. Rapid = ≥ **60 °/s**, counted once per episode.
- **Head reversals:** ≥ 4° steps.
- **Gaze:** label changes per minute (valid gaze only) and iris speed.
- **Pose-estimate jitter** (±0.3°) gives 0 reversals and 0 rapid motions (test).

### 15. Fidget

An episode is a run of excessive-movement frames of 0.6–10 s with:

- the face present;
- no posture shift;
- the head **not** turning fast (< 30 °/s).

Before that last condition, your deliberate head turns counted as fidgeting.

### 16. Temporal aggregation

| Window | Use |
|---|---|
| **Short 15 s** | |
| **Medium 60 s** | The model window |
| **Session** | 10 s bins, bounded memory |

- Raw samples are kept for 90 s.
- The state is re-evaluated every 5 s.
- **Rocking:** the 0.15–0.8 Hz band of the yaw-corrected face size. Head-turn frames are excluded,
  and it needs ≥ 20 s. Before the correction, your head turns scored 0.91; synthetic head turns now score < 0.2 (test).
- **Posture shifts:** only counted while the head faces the same way. Before, there were 35 false
  ones in your recording.

### 17. No effect on cheating risk

Proven by tests (`tests/test_behavior_observation.py`):

- **On / off comparison.** Two workers fed the same restless frames and the same phone / head
  signals at the same times, behaviour forced to "Anxious". Current risk, cumulative risk, levels,
  label, events and risk reasons are **identical** to the worker with the module off.
- **Scheduled path.** The behaviour thread runs with every risk / event / evidence / snapshot entry
  point patched to raise: nothing is called.
- **Label.** The cheating-side label is now only **Focused / Suspicious**. The old keyword rule could
  show "Anxious" next to the risk.
- **Final displayed status (follow-up).** The proctor now sees a final status that combines the two
  separate systems (`core/student_status.py`, display only). The stored label and every risk number
  are unchanged.

  | Cheating Status | Behavioral State | Final Status |
  |---|---|---|
  | No Cheating Indicators | Calm | **Focused** |
  | No Cheating Indicators | Anxious | **Anxious** |
  | Suspicious | Calm | **Suspicious** |
  | Suspicious | Anxious | **Suspicious + Anxious** |

  - Without a Calm / Anxious state (model not trained, not enough data, module off, old sessions,
    a student's own report), the final status is the Cheating Status alone. "Focused" is never
    claimed without an observed Calm.
  - Shown on the dashboard card and in the student panel (Cheating Status, Behavioral State and
    Final Status tiles), in the session report (HTML / PDF) and in the room summary (HTML / CSV).
  - The student never receives it.
  - Tests: `tests/test_student_status.py`.
- **No anxiety percentage leaves the server:**
  - `anxiety_score` was removed from the status;
  - `proba` = {Focused = 1 − Suspicious, Suspicious};
  - the dashboard's Focused / **Anxious %** / Suspicious tiles were replaced by **"Behavioral State"**;
  - the report's "Anxious x %" sentence was removed.
- **Student:**
  - `/student/*`, `/api/sessions`, the exam page and the event stream carry nothing of it (test);
  - **their own finished report also omits it.** The independent review found this leak; there is now a test for html / csv / pdf;
  - the proctor's report has a separate **"Behavioral observations"** section (HTML, PDF, CSV) that
    says these are not violations, not part of the risk score and not a diagnosis.

### 18. Model status

**UNTRAINED.** The dashboard shows **"Model not trained"**.

- `ANXIETY_MODEL_PATH` (opt-in) loads only a file produced by `training/anxiety/train.py`. It
  checks the feature names, classes and format; anything else is refused and logged.
- The synthetic Random Forest (`trained_models/rf_classifier.pkl`) is unchanged and is **not** used for this.

---

## Part 3: Dataset / training preparation (no training)

### 19. Dataset folders

| Folder | Purpose |
|---|---|
| `datasets/phone_proctoring/` | Existing. Class 0 is now **`cell_phone`** (the detector resolves it by name). Hard negatives go in as **background images** with empty label files: microphone, cup, dark fabric, hand, remote, calculator. They are not classes. |
| `datasets/anxiety_behavior/` | `raw/{calm,anxious}`, `clips/{train,val,test}/{calm,anxious}`, `features/{train,val,test}`, `annotations/`. The README documents duration (60 s), fps, minimum resolution, labels, leakage, **split by person**, metadata, balance and privacy. |
| `datasets/audio_proctoring/` | Existing. The README now says honestly: **whisper / shout NOT VERIFIED** with the current YAMNet mapping. |
| `datasets/behavior_features/` | `raw/`, `processed/`, header-only `train/val/test.csv`, README, `feature_schema.json`. For a real-data **CheatingBehaviorClassifier**. The README lists the 14 RF features and which suit cheating; three are excluded: the face-touch proxy, eye openness, session time. |

**Not created on purpose:**

- `face_touch/`, `nail_biting/`, `fidgeting/`: those detectors are landmark / rule based and have
  nothing to train. They are measured against annotations instead (21).
- A gaze dataset: MediaPipe + geometry.

### 20. Label schemas

- **`datasets/anxiety_behavior/label_schema.json`:**
  - classes `calm`, `anxious` (definitions + "not a diagnosis");
  - the 9 action labels: `face_touch`, `hand_near_mouth`, `possible_nail_biting`, `fidgeting`, `body_rocking`, `rapid_head_motion`, `rapid_gaze_change`, `posture_shift`, `normal_movement`;
  - the annotation format.
- **`datasets/anxiety_behavior/feature_schema.json`:** every feature with its unit, the windows,
  model columns vs. model inputs, quality features, abstention limits and rejected features.
- **`datasets/behavior_features/feature_schema.json`:** columns, the use of each feature and the pseudonymous id columns.
- A test asserts that the JSON files match the code.

### 21. Training scripts

| Component | Scripts |
|---|---|
| `training/phone/` | `train.py`, `evaluate.py`, README |
| `training/anxiety/` | `make_splits.py` (by person), `extract_features.py` (the same code as live), `train.py`, `evaluate.py`, `evaluate_actions.py` (rule detectors vs your annotations), README |
| `training/audio/` | `prepare.py` (YAMNet embeddings), `train.py` (a head; YAMNet frozen), `evaluate.py`, README |
| `training/behavioral/` | `prepare.py` (split by student), `train.py`, `evaluate.py`, README |

Shared in `training/_repro.py`:

- seed;
- config (JSON / YAML, unknown keys rejected);
- versioned output, refuse overwrite, refuse `models/`;
- metrics: per-class P / R / F1, macro, confusion matrix CSV; mAP50 / mAP50-95 for the phone;
- resume (YOLO `last.pt`). The tabular models are a deterministic fit of seconds; the dataset SHA-1 is stored.

**Recording tool `tools/record_behavior_dataset.py`:**

- `--consent` is required, and the participant is an anonymous code (P001);
- video optional (`--no-video`);
- it writes frames + **real capture times**, per-frame landmarks / features, window features and meta;
- keys 1–9 mark actions live.

**Opt-in logger.** `BEHAVIOR_FEATURE_LOG=<dir>` writes the RF feature vectors every 5 s with
**pseudonymous** keyed-hash ids, for the cheating dataset. It is off by default.

**What has actually run:**

- **No data:** every script refuses cleanly (exit 3 / "NO REAL DATA AVAILABLE"). Evaluators say "BENCHMARK NOT RUN" and invent no number.
- **Anxiety:** tested end to end on a tiny made-up fixture in a temporary folder (plumbing only) — make_splits → extract → train → a loadable model → evaluate; a second run gives a second folder.
- **Cheating:** prepare → validate → train → evaluate, same kind of fixture test.
- **Audio:** prepare → train → evaluate run once on a synthetic fixture. That smoke run found and fixed a crash in `prepare.py`.
- **Phone:** train (1 epoch) → evaluate ran once on a synthetic fixture in a temporary folder (plumbing only, see 27.6).
- **Real recording:** `extract_features.py` re-analysed a recorded sample (made from your recording, local only). It matched the features computed at recording time (motion 0.0072 vs 0.0077, posture 1.32 vs 1.32 / min).

### 22. Validation scripts

| Script | Checks |
|---|---|
| `tools/validate_phone_dataset.py` | <ul><li>data.yaml class 0</li><li>missing / orphan labels, corrupt images</li><li>label format, unknown class, box outside the image, zero-area box, duplicate lines</li><li>duplicate images inside and across splits</li><li>same file name in two splits</li><li>source / person leakage (`metadata.csv`)</li><li>class counts, background images, empty classes</li></ul> |
| `tools/validate_audio_dataset.py` | <ul><li>structure, unsupported formats, unreadable / empty files</li><li>sample rate (< 16 kHz = error)</li><li>channels, duration ≥ 0.975 s</li><li>duplicates inside and across splits</li><li>speaker leakage (`metadata.csv`), empty categories</li></ul> |
| `tools/validate_anxiety_dataset.py` | <ul><li>meta / consent / anonymous code / personal fields</li><li>duration, resolution, video decodes</li><li>features match the schema, annotation labels and ranges</li><li>duplicates, **person leakage**</li><li>counts / empty classes / imbalance</li><li>features.csv checks</li></ul> |
| `tools/validate_behavior_features.py` | <ul><li>header = schema, labels, finite numbers</li><li>**student leakage**, duplicate rows, empty classes</li></ul> |

- **Exit codes:** 0 usable, 2 errors, **3 no data**.
- **Tested:** each catches the problems it lists.
- **Old validators:** `training/validate_*` now delegate to these.

### 23. Model output folders

`trained_models/{phone,anxiety,audio,behavioral}/` (empty). Every run writes
`<name>_<UTC time>/`.

**Opt-in** for live use:

- `PHONE_MODEL_PATH`: if missing or without a phone class, it is logged and `models/yolov8m.pt` is used;
- `ANXIETY_MODEL_PATH`.

Without them the project behaves exactly as before. A single-class phone model disables
multi-person detection while it is used; this is logged and documented.

---

## 24. Every file changed (vs phase 3, commit 3c52139)

**Modified:**

| File | Change |
|---|---|
| `modules/detection/face_analyzer.py` | gaze hold + immediate end, `gaze_debug`, `face_geometry` |
| `core/student_worker.py` | behaviour thread hand-off, `behavior_state`, summary save, label without "Anxious", `proba` without anxiety, opt-in feature log |
| `core/session_manager.py` | behaviour scheduler, summary at submit / logout |
| `core/ai_scheduler.py` | `backlog()` |
| `core/diag.py` | gaze decision in the DIAG line / record |
| `db_models.py` | `exam_sessions.behavior_summary` + automatic column upgrade |
| `routes/api_reports.py` | behaviour section for the proctor side only |
| `modules/reporting/session_report.py` | "Behavioral observations" section (HTML / PDF / CSV), "Anxious %" removed |
| `templates/proctor/dashboard.html` | Behavioral State tile instead of the percentage tiles |
| `modules/detection/phone_detector.py` | opt-in `PHONE_MODEL_PATH`, `cell_phone` name |
| `tools/live_diag.py` | gaze exceedance / reasons in the verdict |
| `benchmark/load_test_real_frames.py` | behaviour metrics |
| `datasets/README.md`, `datasets/phone_proctoring/{README.md,data.yaml}`, `datasets/audio_proctoring/README.md` | docs, class 0 `cell_phone` |
| `training/dataset_status.py` | the new datasets |
| `training/validate_phone_dataset.py`, `training/validate_audio_dataset.py` | wrappers to `tools/` |
| `tests/test_misc_infra.py` | requirement changes: class name, new dataset folders |

**New:**

| Area | Files |
|---|---|
| Behaviour module | `modules/behavior/{__init__,schema,motion,hands,features,classifier,monitor,offline}.py` |
| Cheating classifier | `modules/ml/cheating_classifier.py` |
| Hand model | `models/hand_landmarker.task` (7.8 MB), `models/HAND_LANDMARKER_SOURCE.md` |
| Tools | `tools/{fetch_behavior_models,record_behavior_dataset,validate_phone_dataset,validate_audio_dataset,validate_anxiety_dataset,validate_behavior_features}.py` |
| Training | `training/{README.md,_repro.py}`, `training/phone/*`, `training/anxiety/*`, `training/audio/*`, `training/behavioral/*` |
| Datasets | `datasets/anxiety_behavior/*`, `datasets/behavior_features/*` |
| Model folders | `trained_models/README.md` + 4 empty folders |
| Benchmarks | `benchmark/phase4/{hand_cost_bench,behavior_replay}.py` |
| Tests | `tests/{test_gaze_reliability,test_behavior_observation,test_data_preparation}.py` |
| Report | this report |

## 25. Performance before / after (this 2-core machine)

**Hand landmarks**, measured *before* integration (`benchmark/phase4/hand_cost_bench.py`,
320×240 exam frames):

| | CPU per call | p95 |
|---|---|---|
| Hand landmarks | 9–14 ms | 18–27 ms with hands in view |
| FaceAnalyzer, for comparison | 12–13 ms | |

**Server load test** (`benchmark/load_test_real_frames.py`, real face frames, the real pacing,
in process). Each cell is phase 3 (two runs) → phase 4.

| Students | 1 | 5 | 10 |
|---|---|---|---|
| Head / gaze fps per student | 3.0, 3.0 → **3.0** | 3.0, 3.0 → **3.0** | 2.9, 3.0 → **2.9** |
| Face step p50 (ms) | 15.4, 16.3 → 15.6 | 24.8, 25.9 → 26.5 | 29.6, 30.6 → 31.4 |
| YOLO interval (s) | 1.0, 1.0 → **1.0** | 2.3, 2.3 → **2.3** | 7.5, 7.5 → **7.5** |
| YOLO step p50 (ms) | 653, 623 → 629 | 949, 914 → 937 | 1496, 1398 → 1474 |
| Proctor grid frames / student / s | 3.90, 3.93 → 3.93 | 3.63, 3.60 → 3.63 | 3.07, 3.14 → 3.07 |
| Frame age p50 / p95 (ms) | 36/66 → 33/66 | 33/67 → 30/67 | 35/69 → 35/68 |
| CPU (avg, % of one core) | 76, 74 → 73 | 182, 179 → 182 | 184, 182 → 181 |
| RAM max (MB) | 2127, 2130 → 2193 | 2160, 2167 → 2206 | 2179, 2161 → 2213 |
| Behaviour samples / student / s | – → 3.0 | – → 2.2 | – → 1.4 (detection first) |

The earlier design, with behaviour inside the face thread, measured **2.0** fps at 10 students.
That design was rejected.

**Server CPU with one simulated student** (preview + AI, head-turning video, 30 s):

| | Server CPU, % of one core |
|---|---|
| Phase 3 | 66.7 % |
| Phase 4 | **71.2 %** |
| Phase 4 with `BEHAVIOR_ANALYSIS=0` | 68.9 % |

The behaviour module costs about **2–4 % of one core per student** while the student moves. It
costs less when the student is still: hands every ~3 s, no FFT on still frames.

**Selected student's live video, real Chromium.** Server, student browser and proctor browser
all ran on this one 2-core machine, your one-computer test setup (`hidden_window_bench.py`).
Each result is a pair of 15 s windows; runs alternated base / new:

| Run | Displayed fps |
|---|---|
| Phase 3 | 26.3 / 28.3 and 25.8 / 27.7 |
| Phase 4 | **25.1 / 25.9** and **23.8 / 25.7** |

- **Head / gaze rate:** unchanged (3.3 fps).
- **Capture → arrival p50:** 18–19 → 21–23 ms.
- **Video:** on this saturated single machine the selected student's video is about 1–2.5 fps
  lower (−5 to −9 %); between runs the noise is about 2 fps.
- **Earlier configurations:** with hands every 1 s the gap was larger, so the hand checks were
  reduced (11).
- **To get the old numbers back:** `BEHAVIOR_ANALYSIS=0`, or `BEHAVIOR_HANDS=0` for only the hands.

## 26. Tests

| Run | Result |
|---|---|
| Phase 3 baseline | 199 passed |
| **Phase 4 full suite** | **271 passed, 0 failed** |
| After the final-status follow-up | **304 passed, 0 failed** (+33 in `test_student_status.py`) |
| JS client test | passed |

The phase 4 total breaks down as:

- the 199 earlier tests, of which 2 were changed in `test_misc_infra.py` for the requirement changes (class name, new folders);
- **+15 gaze tests**;
- **+27 behaviour tests**;
- **+30 data-preparation tests**.

The one remaining warning is pre-existing and also appears on phase 3: a test-harness thread in
`test_isolation_concurrency`.

**Independent review.** A separate agent reviewed the full diff. It reported two reproduced
problems, both now fixed, each with a regression test that fails without the fix:

- the student's own report showed the behavioural observations;
- the gaze hold could stretch a 3.3 s look into a violation.

It also flagged inline behaviour work on the detection path, live vs. training sampling mismatch,
a leftover way to recover the old anxiety value from `proba`, environment parsing, and weak tests.
All of these were fixed.

## 27. NOT VERIFIED

1. **Pure "eyes up" and eyes-only "looking down to the lap" by you:** not in your material. Down
   needs eyeLookDown ≥ 0.81 for you; your blinks reach 0.72.
2. **Your moderate left glance** (0.56–1.04 × the threshold) is not classified. Thresholds were
   not lowered (see 2).
3. **Calibration delay:** head / gaze can still start only after up to **45 s** when the head
   moves at the start. Not changed.
4. **Behavioral State:**
   - **no trained model, no accuracy**;
   - every behaviour limit is an engineering default, measured only on your one recording + test
     photos: fidget, posture, rocking, near-mouth 0.35 and at-mouth 0.20 face widths, touch rule,
     60 °/s;
   - rocking was never observed on real footage;
   - the dev heuristic called your test session "Anxious", because your deliberate test movements
     produced head reversals of 30 / min and fidgeting of 7 / min. It is a development aid, not a judgement.
5. **Hands:**
   - brief touches (< ~1.5 s) can be missed;
   - a hand in front of the face counts as a touch (2-D);
   - nail-biting is a candidate only.
6. **Phone fine-tune, YAMNet head, cheating RF:** no real data, so no real training or evaluation was run.
   - `training/phone/train.py` (1 epoch, 64 px) then `evaluate.py` ran once on a synthetic fixture in a temporary folder, to check the YOLO plumbing only.
   - It produced a versioned folder (`weights/best.pt` + `last.pt` for `--resume`, `metrics.json`, `metrics_test.json`, confusion-matrix CSVs); exit 0.
   - Its numbers are meaningless and are not reported. Nothing was written to `trained_models/phone/`, and `models/yolov8m.pt` is untouched.
7. **Whisper / shout** detection with the current model.
8. **Your hardware (Windows):**
   - performance;
   - `tools/fetch_behavior_models.py` download path (here only the build-from-wheel path ran);
   - `record_behavior_dataset.py` with a live camera (here only with a video file).
9. **Pseudonymous logs.** The opt-in feature log is pseudonymous, not anonymous: the key holder can re-link it.

**Your next check.** Run `python tools/live_diag.py --only 1,6,7,8,9` and send
`live_diag_report.json`. Each eye step now prints the exceedance of its direction and why it lost.
