# FINAL REAL RUNTIME REPAIR REPORT — `exam_proctor_detection_fixes`

Labels used: **PASS** = proven here · **FAIL** = proven broken · **PARTIAL** = partly works ·
**NOT VERIFIED** = this environment cannot prove it (no webcam, no Windows, no second device).

Every "before" result below was reproduced on the **unmodified** project
(`exam_proctor_detection_fixes.zip`, kept as a pristine copy) before any line was changed;
every "after" result was measured on the repaired copy with the same harness.
Nothing from the earlier `exam_proctor_latest_2026-09-14` work was copied into this project.

---------------------------------------------------------------------------------------------

## 1. Exact project path actually tested

| | |
|---|---|
| Project tested and repaired | `/home/claude/dfix/exam_proctor_detection_fixes` (your zip, unpacked unchanged, baseline committed in git before any change) |
| Pristine copy used for every "before" measurement | `/home/claude/dfix_baseline/exam_proctor_detection_fixes` |
| Loaded modules (printed by importing them) | `app.py`, `run.py`, `config.py`, `routes/api_student.py`, `routes/api_proctor.py`, `modules/detection/face_analyzer.py`, `modules/detection/phone_detector.py`, `modules/detection/audio_analyzer.py`, `core/risk.py`, `core/student_worker.py`, `core/session_manager.py` — all from the folder above |
| Templates | `templates/student/exam.html`, `templates/proctor/dashboard.html` (same folder) |
| Models | `models/blaze_face_short_range.tflite`, `models/face_landmarker.task`, `models/yolov8m.pt` (52 MB, real weights), `models/yamnet/` (TF SavedModel + class map) |

**Reported first (as required): your real log was produced by a DIFFERENT, OLDER project.**
Every path in the supplied log is `C:\Users\radim\Downloads\exam_proctor_latest_2026-09-14\exam_proctor\…`
(the string "detection_fixes" occurs 0 times in 3 590 lines). The log, and the screenshots taken with it,
therefore describe the old folder, run with the system Python
`C:\Users\radim\AppData\Local\Programs\Python\Python310` (no virtual environment). The message
"No face detected in frame" in the screenshots does not even exist in this project's live code path
(it only appears in `setup_demo.py` demo data). Every symptom was therefore re-checked on this project.

`run.py` now prints the project folder, the Python executable and the PROCTOR_DIAG state at start-up,
so the folder that is really running is visible in the first lines of every log.

## 2. Exact Python / environment used here

Linux sandbox, 2 vCPU, 8 GB RAM, **no webcam, no microphone, no Windows, no second device**.
`/home/claude/venv` — Python 3.11.15, numpy 1.26.4, scikit-learn 1.7.2 (the pickle's version, as pinned),
TensorFlow-CPU 2.21.0, MediaPipe 1.1.0, PyTorch 2.14.1 (CPU), Ultralytics 8.4.174, OpenCV 4.11, Flask 3.1.3.
Real browser tests: Playwright Chromium with a fake camera (a real face photo) and a fake microphone (real speech).
Sandbox-only: `triton` (a CUDA package pulled in by torch) segfaulted when imported together with TensorFlow and
was uninstalled; it is not a project dependency.

Baseline of your own test suite on the unmodified project: **149 passed, 0 failed, 1 warning**; Node client test: all
assertions passed. The suite passed although `/student/frame` returned 500 with a real face — no test serialised
a real-face status through HTTP.

## 3. Root cause of `POST /student/frame` → 500

Reproduced on the unmodified project with **real roles in separate cookie jars** (student, proctor, admin)
and a real face photo encoded exactly like `exam.html` (320×240, JPEG q 0.65, raw `image/jpeg`):

```
POST /student/frame  -> 200, 200, 500, 500, 500      (500 as soon as the AI had analysed one face frame)
TypeError: Object of type bool_ is not JSON serializable
no-face frames       -> 200, 200, 200, 200
```

`modules/detection/face_analyzer.py` (line 413 of the original):
`blink = gi is not None and gi[2] < max(0.06, self._neutral[4] * 0.55)` — `self._neutral` is a NumPy array, so
the comparison returns `numpy.bool_`. It is returned as `eyes_closed`, copied into the worker status and listed in
`_FRAME_KEYS` of `routes/api_student.py`, so `jsonify()` fails. With no face, `gi` is `None` and the value is a
Python `False` — which is why the error only appears when a face is visible.

## 4. Exact non-JSON-safe field(s)

A recursive audit of the complete worker status (JSON path, type, value — now `core/json_safe.find_unsafe`) on real
face, no-face, phone, two-person and turned-head frames found exactly one field:

```
[json-audit] worker.get_status().eyes_closed -> numpy.bool_ = False
```

(`deviation_from_neutral.x/.y` were `numpy.float64`: serialisable because that type subclasses `float`, but also
converted now.)

**Fix, at the correct boundary:** `bool()` at the source in `face_analyzer.py`; `to_json_safe()` where detector
output becomes API state (`StudentWorker._run_pipeline` status update, audio results). Mappings:
`np.bool_→bool`, `np.integer→int`, `np.floating→float` (NaN/inf → `null`), `ndarray→list`; nothing is turned
into a string. After: 5/5 frames 200 with a real face (`01_frame_poll_after.txt`); the real analyzer output and the full status audit are clean.

## 5. Root cause of `GET /proctor/students/poll` → 500

The same field: `SessionManager.get_all_statuses()` → `worker.get_status()` → `_enrich_statuses()` →
`jsonify(statuses)`. Before: **500 for the proctor and 500 for the admin**. After: 200, the student is listed.

## 6. Why the dashboard showed "0 Active"

The poll response crashed (5), so `pollStudents()` never received a list. The dashboard itself kept polling and
recovers by itself once the server answers. Proven in real Chromium after the fix: Active **0 → 1 automatically,
the tile appeared 0.95–1.42 s after "Join Exam"**, no page reload.

Two further dashboard defects were found while proving "the proctor sees the student", both reproduced in Chromium:

* **Only the first tile's live video refreshed.** `pollStreams()` iterated `#student-grid [data-sid]`, which also
  matches each card's "View Report" button; the first button threw (no `<img>`) and aborted the loop.
  Before: 2 students → one tile 0 fps; 5 students → four tiles 0 fps. After: every tile 3.5–4.1 fps.
* **The live alert feed and the event counters never showed anything.** `loadRecentEvents()` clears `#alert-feed`
  (removing the `#alert-empty` placeholder), after which `pushAlert()` threw on every event.
  Before: 4 SSE events received, 0 displayed, counters 0. After: 4 displayed, audio 3 / total 3.

## 7. The admin-as-student session

In your log the **admin** account started the exam (`[Worker:admin]`, `student_id=1 name=admin`) — in the old
project. In this project `routes/api_student.py` already contained a `_require_student` decorator (students + admin)
but **no endpoint used it**: any logged-in role could start an exam. Proven on the original code: `student1`,
`admin`, **`proctor1` and `proctor2`** all got 200 on `/student/session/start` and a worker was created for each.
The admin's own session was visible to the room's proctor (scoping is by room), so it was not the cause of
"0 Active" — the 500 in (5) was.

Policy implemented (explicit, RBAC not weakened): only **students** take exams; an **admin** may take one as an
explicit **TEST session** (`test_session: true`, `session_role: "admin"`, a warning line in the server log, an
"ADMIN TEST" badge on the proctor tile); **proctors and other roles get 403** on every exam endpoint and are
redirected from `/exam` to their dashboard. Exception, unchanged: `GET /student/rooms` (read-only list of open rooms,
no session, no worker) is still `@login_required` only. Ownership scoping (a proctor only sees students of his rooms; a foreign
proctor gets `[]` / 403) was re-verified and is unchanged.

## 8. Face detection

Real portraits framed like the exam page (4:3, 320×240, JPEG 0.65), real BlazeFace + FaceLandmarker:
**40/40 faces found** at normal distance; at a far distance 38/40 (two faces < 2 % of the frame are dropped by the
existing size rule — unchanged). No colour-space, orientation, decoding or resizing defect was found; no face
threshold was changed. Detector score, box area %, brightness, blur, landmark count and the exact reason a face is
rejected are now in the PROCTOR_DIAG line.

**Calibration (re-audited from scratch).** Any single ineligible frame (e.g. gaze confidence 0.56 < 0.60) cleared
every collected sample. Real webcam frames of one person with one such frame in six: **before 46.4 s (only the 45 s
fallback), after 10.4 s (strict calibration)**. Ineligible frames are now skipped and counted; long gaps and the
stability test still reset. Accepted / rejected / reset counters, last rejection reason, time-to-ready and method
(strict / fallback) are reported per student. Calibration state remains per student (`get_state/set_state`, test added).

## 9. Head — four directions

Sign convention verified on **227 real frames**: correlation pitch ↔ nose-drop −0.918 (+pitch = head UP),
yaw ↔ nose offset −0.911 (−yaw = nose to image-right = the student's own LEFT). The analyzer is correct for the raw
camera image. Defects found and fixed:

1. **LEFT/RIGHT swapped by the exam page.** `grabBlob()` drew the video with `setTransform(-1,0,0,1,w,0)`; `drawImage`
   ignores the CSS mirror, so this **mirrored** the uploaded frame. Proven in Chromium with a fake camera carrying a
   red mark in its top-left corner: before, the uploaded frame had the mark on the right; after, on the left. On real
   frames the mirrored input turns a LEFT turn into "Head Right". The student still sees a mirrored preview (CSS only).
2. **Large turns produced no head direction.** Frames with |yaw| > 40° or |pitch| > 35° were "poor"
   (`excessive_head_angle`), head confidence decayed above 20°, and the nose leaving the detector box invalidated the
   landmarks. Real frames of one person turned −37° … −56°: before `head_pose_valid=False` on most frames and the
   orientation stayed "unknown"; after, "Head Left" on every frame and the 4 s gate is reached. Head direction now uses
   a head-specific quality (one face, landmarks inside the image, landmark face = detector face, light / blur / size);
   gaze keeps the strict rules.
3. **The 4 s timer restarted whenever the gaze label changed.** On the real "head up" sequence of `test_real_head_up` the
   original labelled the frames head_deviation → combined_deviation → **normal** (gaze "Unknown" with the head up was
   "normal") → …; every change restarted the timer: durations 0.0 / 0.8 / 0.0 / 0.0 / 0.8 / 0.0 / 0.8 / 0.0, never 4 s.
   Repaired: 0.8 → 1.6 → … → 4.0 → 5.6 s on the same frames (`12b_head_up_timer_before_after.txt`). On another real
   sequence (`12_head_gaze_calibration_before.txt`) the label happened to stay constant and the original did reach 4.0 s,
   so the original failure depends on the gaze label. The "normal" frames are not a separate defect. In the original
`_update_orientation`, a head_deviation whose timer has just restarted is shown as "normal" until the dwell time is
reached. Head pose confidence on those frames was 0.73–0.75 in both versions. Episodes are now timed per direction.
4. **One invalid frame restarted a held turn** (detector miss, a background face). Up to 2 s of invalid frames are
   now tolerated; longer gaps still end the episode.

   Two related gating changes, so that the turn being measured does not switch head measurement off:
   - Head direction is also valid while calibration is `degraded`; the original required `ready`.
   - A frame that is "poor" only for gaze but has a usable head quality (≥ `QUALITY_USABLE`) no longer starts the
     calibration-degradation timer.

   No numeric face, gaze or head threshold was changed.
5. **First-match labelling** could call a 50° LEFT turn "Head Up"; the dominant exceedance is used now.

| Real-frame check (simulated 1.25 AI fps clock, real MediaPipe) | Result |
|---|---|
| Head LEFT, large (−37…−56°) held 9.6 s | head_deviation **left**, 4.0 s reached → event-eligible |
| Same frames mirrored (old page) | "Head Right" (swap proven) |
| Head RIGHT (+29°) | head_deviation/combined **right**, 4.8 s |
| Head UP (+29…+35° vs baseline) | **up**, 4.0 s reached |
| Head DOWN | **NOT VERIFIED** on a real head-down sequence (none available); sign and logic covered by the 227-frame correlation and unit tests |
| Brief 0.8 s turn | no event, duration 0 |

Fast or brief movement still never creates an event (4 s gate unchanged, tested).

## 10. Gaze — four directions

* **LEFT / RIGHT: real iris landmarks.** Same person looking straight → looking to her left / right
  (`img10 → img4 / img1`): "Looking Left" / "Looking Right", eye_deviation, 4.0 s reached. Independently confirmed by
  the landmarker's own eye-look blendshapes (eyeLookOut/In 0.73 / 0.49). The mirror swap affected gaze identically
  and is fixed by the same change.
* **DOWN: limitation, honestly reported.** On real frames with downcast eyes the lid-based eye openness is
  0.02–0.09, below the blink threshold, so those frames are classified "Eyes Closed" and never "Looking Down"
  (test added that documents it). The face_landmarker blendshape `eyeLookDown` separates them well on the same frames
  (0.75–0.91 looking down vs ≤ 0.56 looking ahead), but switching to it would also turn head-down + eyes-down into
  the existing "reading_down" state, which by design creates no event — i.e. it could suppress today's Head-Down
  event. It needs your webcam data first; not implemented. A head tilted ≥ 12° down still produces "Head Down".
* **UP: NOT VERIFIED** — no real looking-up frames were available; logic unchanged.

## 11. Phone — findings and exact failure stage

**Correction to an earlier draft.** The phone numbers in an earlier version of this section came from a probe script
whose import path still pointed at the OLD folder (`exam_proctor_latest_2026-09-14`). All numbers below were
re-measured on THIS project, and the decision was changed because of what the new measurements showed.

A per-frame **stage trace** is now part of the detector result (`phone_trace`) and of PROCTOR_DIAG / `live_diag.py`.
It records raw YOLO boxes (confidence, box, area %), verifier score and decision, tracks, ensemble tier and a stage label:
- NONE (no box = YOLO MISS if a phone is visible)
- VERIFIER REJECTION
- TRACKER: building evidence
- **TRACKER GATE: weak evidence** (seen ≥ 2 times but the confidence-weighted buffer is < 0.40)
- ENSEMBLE MONITOR
- CONFIRMED

This is diagnostic only; it does not change any decision.

**Where real phones stop (original code, real photos held 6 AI frames; `11_phone_trace_original_vs_presence_experiment.txt`).**
The TRACKER GATE stage is labelled "weak evidence" — YOLO 0.18–0.54 on real phones — which this report classifies as a MODEL LIMITATION.

| Real phone | YOLOv8m cell-phone box | verifier | tracker buffer (confirms ≥ 0.40) | result | stage |
|---|---|---|---|---|---|
| woman on the phone, 640×480 | 0.29–0.35 in **6/6** frames | ACCEPT 0.46–0.49 | 0.387–0.394 | NONE ×6 | **TRACKER GATE** |
| man on the phone, 640×480 | at-ear box 0.37–0.49 in 6/6; a 2nd box on the hand/phone 0.19–0.31 | MONITOR 0.25 / 2nd box ACCEPT 0.64–0.67 | 0.25–0.26 / 2nd box 0.40–0.43 | MONITOR in 5/6 (ensemble 0.50–0.55 < 0.55) | TRACKER GATE / ENSEMBLE MONITOR |
| cadet with phone, 640×480 | 0.29–0.37 in 6/6 | MONITOR 0.25 | ≤ 0.38 | NONE ×6 | TRACKER GATE |
| woman, 320×240 (exam frame) | 0.44–0.54 in 6/6 | MONITOR 0.34–0.42 | 0.32–0.34 | MONITOR in 4/6 (single-frame rule: YOLO ≥ 0.50) | TRACKER GATE |
| man, 320×240 | 0.40–0.45 in 6/6 | MONITOR 0.25 | 0.24–0.25 | NONE ×6 | TRACKER GATE |
| cadet, 320×240 | 0.18–0.26 in 4/6, no box in 2 | ACCEPT 0.52 / MONITOR | ≤ 0.34 | NONE ×6 | TRACKER GATE + **YOLO MISS** |

The tracker's buffer stores, per frame, `0.55·YOLO + 0.45·verifier` (× 0.7 for MONITOR). The file documents this two ways.
`_effective_score()` and the module header describe a confidence-weighted buffer. The buffer comment and the `buffer_score`
docstring describe presence ("1.0 = phone", "fraction of slots with a phone signal"). In effect it is a **second
confidence gate**: it is not a crash, a reset or a sampling problem. Real phones fail it because the generic COCO YOLOv8m gives them only 0.2–0.5 at these sizes.

**A fix was tried and NOT shipped.** The tried change made the tracker buffer record presence (ACCEPT 1.0 /
MONITOR 0.7), which leaves YOLO and the verifier to the ensemble. Measured on 87 real images framed like the exam page
(`11b_phone_false_positive_sweep_87_images.txt`, 5 AI frames each):

| | original (= shipped) | presence buffer (tried) |
|---|---|---|
| 5 images with a real phone: CONFIRMED / MONITOR / none | 0 / 2 / 3 | **3 / 2 / 0** |
| 82 phone-free images: CONFIRMED (+70 each) | **0** | **2** — a hand-held microphone, dark dress fabric |
| 82 phone-free images: MONITOR (+16) | 1 (microphone, 1 frame of 5) | 1 (statuette base) |
| coffee cup in a background person's hand | not confirmed | **CONFIRMED** (640×480 and 320×240) |

Better recall was bought with false +70 accusations. YOLO and the verifier give a cup or a microphone the same evidence as these real phones:
- the cup: YOLO 0.17–0.33, verifier ACCEPT 0.53–0.54 (11_)
- the microphone: YOLO 0.34, verifier ACCEPT 0.57 (11c_)

No tracker logic can separate them. That is a model
limitation, and choosing the trade-off is a threshold decision you ruled out. **`phone_tracker.py` is therefore
byte-identical to your upload.** Two tests now guard this:
- `test_tracker_keeps_the_original_phone_operating_point`
- `test_real_phone_free_photos_never_confirm_a_phone`, which fails with the presence buffer: the microphone is CONFIRMED in 5 of 6 frames
  (`11c_guard_tests_fail_with_presence_experiment.txt`; 3 of 5 frames in the 11b sweep).

**Classification:** real phones at the exam's 320×240 fail at the **TRACKER GATE** because of a **MODEL LIMITATION** (low
YOLO confidence), sometimes as a **YOLO MISS**. They do not fail because of a verifier rejection, a state reset, a pipeline
crash or the ensemble. The real fix is a phone model trained on webcam images (the project already has `training/`).
Alternatively, you could choose a lower operating point after measuring false confirmations on your own exam-room footage.

**Fixed (risk side, see 16):** a phone held continuously while the AI ran only every 3.5 s added +70 cumulative on
**every** frame, because each frame looked like a new episode.

Not claimed: phone accuracy on your webcam (NOT VERIFIED). `python tools\live_diag.py` step 10 reports the stage per frame.
At ≥ 10 students on this 2-core machine the AI interval per student exceeds 4 s, so the tracker can no longer collect
2 observations within 4 s. That is a **SAMPLING FAILURE** under load, see 24.

## 12. Audio / YAMNet

| Check (real model, real files) | Result |
|---|---|
| Model | `models/yamnet` SavedModel loaded with TF 2.21, 521 classes, official class map, 6.3 s load, 12–24 ms per 2 s window |
| Real speech (JFK) | **speech 0.97–1.00** in every window |
| Keyboard typing (ESC-50) | "typing" 1.00, not suspicious |
| Dog / rain / clapping | "other", not suspicious |
| Coughing | "speech" 0.54 → a false positive with the current (uncalibrated) 0.45 threshold |
| Digital silence | RMS gate, no inference |
| Whisper / shout | **NOT VERIFIED** (no real recordings) |
| End to end in Chromium | fake microphone (speech) → browser 16 kHz PCM → `/student/audio` → YAMNet → `audio_speech` events → risk → DB → proctor alert feed |

Fixed: confirmed audio events raised only **current** risk, but the resume / finalise paths counted them in
cumulative risk (inconsistent) — they now add their configured +20 to cumulative risk. Behaviour to be aware of
(unchanged design): continuous talking produces one audio event per 10 s cooldown, each +20.
Whether TensorFlow is installed on your PC is unknown: without it the backend is the clearly labelled
"energy-variance fallback"; `live_diag.py` prints which backend runs.

## 13. Live preview — root cause and measurements

The preview path was already independent of YOLO / MediaPipe / YAMNet / DB and "latest frame wins" (one slot,
older frames replaced, ETag/304); it was not rewritten. Defects found: mirrored preview (9.1), the multi-tile refresh
bug and the alert-feed crash (6), the zoomed student view showing **0 fps** whenever Chart.js could not be loaded
(no internet on an exam LAN: `new Chart` threw before the live refresh started → now guarded, 5.9 fps), and with the
Tailwind CDN unreachable **all views of the exam page were shown at once** (the `hidden` class was undefined → a
one-line local fallback rule).

Measured in Chromium (fake camera; client and server on the same 2 cores): student preview upload 13 /s median;
proctor tile 4.0 fps (bounded by the 250 ms stream poll), frame age p50 28–38 ms / p95 53–72 ms, zoomed view 5.9 fps.
A 50 ms zoom refresh was tried (6.4 fps): no measurable benefit → **reverted**. The 10–20 fps target is not reached
by the JPEG-polling design on this hardware — PARTIAL.

## 14. "Stream: Error"

In this project the student "Stream" label is driven by the freshness of accepted preview frames. Proven in Chromium:
uploads blocked for 8 s → "Live" → "Reconnecting…" after ~5 s → **"Live" again 1.6 s after the network returned**
(`06_browser_e2e_after.json`, `outage_labels`; an earlier, unshipped run showed 0.5 s); no
permanent error state. On the original code the visible symptom of the 500 was "Analysis: Server error" (screenshot of
the unmodified page in Chromium).

## 15. Current Risk

Unchanged mechanism: per-type points, 45 s half-life, per-type caps. Test: after a confirmed phone and 20 calm
minutes current risk is **Low** (< 30 %).

## 16. Cumulative Risk

Starts at 0, only grows, never decays, clamped at 100 %, phone +70 / multiple persons +55 once per confirmed episode.
Defects found and fixed (each reproduced before). The rows up to "logout" are one continuous run of each code version
(`03_persistence_before.txt` / `_after.txt`); the rows below come from `04_episodes_*`:

| Case | before | after |
|---|---|---|
| Phone confirmed | 0.70 | 0.70 |
| Page refresh / re-join | new session, cumulative **0.70 → 0.00** (first session finalised at 0.70) | same session, 0.70 |
| + 2 speech windows | cumulative **0.00** (current 0.20) | 0.90 (+0.20) |
| + tab hidden | cumulative **0.00** (current 0.53) | 1.00 (+0.33, clamped) |
| Worker lost → resumed from DB | 0.00 → **0.53** (jump) | 1.00 → 1.00 |
| Logout + login + re-join | new session, **0.00** | same session, 1.00 (logout no longer submits the exam) |
| Phone held 40 s, 1 AI frame/s, then resume | live 0.70, after resume **1.00** | 0.70 / 0.70 |
| Phone held 40 s, 1 AI frame / 3.5 s | live **1.00** | 0.70 |
| 2 persons 60 s, sparse frames, then resume | **1.00** | 0.55 / 0.55 |
| Phone 5 s, gone 20 s, phone 5 s (two episodes) | 1.00 | 1.00 (70 + 70, clamped) |

Mechanics: the original ended an episode on any gap longer than `CONTINUITY_GAP` (2.5 s) between positive frames,
so with one AI frame every 3.5 s every frame was a new episode. An episode now ends after ≥ 2 analysed frames
*without* the signal (then the original 2.5 s gap rule applies), or after 30 s without any observation; every event row stores the cumulative points it really added
(`behavior_events.cumulative_points`, nullable, added by the project's own idempotent `ensure_schema()`; older rows
fall back to the previous EPISODE rule), so resume and finalisation rebuild exactly the live value.

## 17. Proof that cumulative never decreases

`_cumulative_add()` is the only writer (adds `max(0, points)`, clamps at 1.0); restore rebuilds from stored points.
Tests: `test_cumulative_never_decreases_and_is_capped`, `test_face_return_lowers_current_but_never_cumulative`,
`test_current_low_cumulative_70_overall_high_final_70` (40 × 30 s of calm after a phone: cumulative stays 0.70),
plus the persistence tests in 16.

## 18. Proof that Final Risk == Cumulative Risk

`stop_session()` stores `final_score = cumulative_risk`, `final_risk = overall_level`; an interrupted or suspended
session is finalised from the same per-row points. Test through the real HTTP API: current **Low**, cumulative **0.70**,
overall **High** → `/student/session/stop` returns final 0.70 / High → DB `final_score 0.70`, `final_risk High` →
`/proctor/sessions` shows 0.70. A suspended session that is never resumed is finalised by the watchdog with its
cumulative risk (test: 0.55 / Medium). The student page now shows "Exam total (cumulative)" next to the current risk;
the dashboard already distinguished both.

## 19. Event / risk persistence

| Scenario (real server `run.py`, real HTTP, cookies) | before | after |
|---|---|---|
| Server killed with `kill -9`, restarted, same browser cookie | same session; cumulative **0.00 before → 0.33 after** (inconsistent) | same session, **0.33 → 0.33**; re-join → same session; proctor card 0.33 Medium, stream live |
| Refresh / logout / worker loss | see 16 | see 16 |

## 20. Every file changed / 21. Why

| File | Change | Why (proof) |
|---|---|---|
| `modules/detection/face_analyzer.py` | `bool()` on `eyes_closed`; float casts; head-specific quality (`_head_quality`), large angles no longer invalidate head direction; calibration skips ineligible frames + counters; orientation timed per direction; 2 s invalid-frame tolerance; dominant head label; diagnostic fields (raw/neutral pose & gaze, detector score, landmark count) | §3, §8, §9 |
| `core/json_safe.py` *(new)* | `find_unsafe` (JSON path / type / value) and `to_json_safe` | §3–§5 |
| `core/student_worker.py` | JSON-safe status boundary; episode continuity on observed absence; cumulative points stored per event; audio + integrity add cumulative; role flag; per-signal decisions + PROCTOR_DIAG hook; `phone_stage` in status | §4, §11, §12, §16, §23 |
| `core/session_manager.py` | start = continue the same-room open session; `suspend_session` (logout); exact cumulative rebuild; db-only cards show cumulative; role / ADMIN TEST logging | §7, §16, §19 |
| `core/risk.py` | `cumulative_points_of()` (stored points, legacy fallback) | §16 |
| `core/diag.py` *(new)* | PROCTOR_DIAG per-frame / per-audio-window records (console + optional JSONL) | spec |
| `db_models.py` | nullable `behavior_events.cumulative_points` via the existing `ensure_schema()` list | §16 (only schema change; needed for exact resume) |
| `modules/detection/phone_detector.py` | `phone_trace` stage diagnostics incl. the "TRACKER GATE: weak evidence" label (no behaviour change) | §11 |
| `routes/api_student.py` | `_require_student` applied to every exam endpoint; role passed to the session; risk fields in responses; final risk in stop response; DB connection released after auth | §7, §18, §24 |
| `routes/api_proctor.py` | DB connection released after auth (`_require_proctor`) | §24 |
| `routes/auth.py` | logout suspends instead of submitting; DB connection released before the password hash | §16, §24 |
| `app.py` | `/exam`: proctors redirected, other non-student roles 403 | §7 |
| `run.py` | prints project folder, Python, PROCTOR_DIAG | §1 |
| `templates/student/exam.html` | un-mirrored upload; "Exam total (cumulative)" display | §9, §18 |
| `templates/proctor/dashboard.html` | tile refresh only iterates cards; null-safe alert placeholder; Chart.js guard; ADMIN TEST badge | §6, §13, §7 |
| `static/css/design-system.css` | `.hidden` fallback when the Tailwind CDN is unreachable | §13 |
| `tools/live_diag.py` *(new)* | PowerShell webcam/microphone diagnostic (25) | spec |
| `tools/fetch_test_assets.py` *(new)* | downloads the third-party media for the real-media tests | §22 |
| `evidence/runtime_repair/` *(new)* | before/after outputs, browser runs, load-test JSON, phone traces, head/gaze traces, YAMNet run | all sections |
| `benchmark/load_test_real_frames.py` *(new)* | load test with real face frames and the real server pacing (the existing `load_test_inprocess.py` is unchanged) | §24 |
| `tests/test_runtime_repairs.py`, `tests/test_real_runtime_media.py` *(new)* | regression tests | §22 |

Not changed: model files, `phone_tracker.py` (a tried change was measured and reverted, §11), YOLO / verifier / ensemble / face / gaze / audio thresholds, event weights, cooldowns,
pacing, scheduler, detector pool, CSRF / login throttle / ownership checks, reports, dependencies.

## 22. Tests added

`tests/test_runtime_repairs.py` (21 tests, run in every suite): NumPy bool/int/float serialization; real FaceAnalyzer
output plain Python; `/student/frame` never 500 and poll lists the student (real MediaPipe); role isolation
(student / explicit admin test / proctor 403); poll scoping; preview latest-frame-wins + snapshot ETag/304; page uploads
the un-mirrored frame; face-state round trip; calibration with an ineligible frame; head dominant direction + invalid-frame
tolerance; head quality ignores the angle; the tracker keeps the original phone operating point;
one phone episode = +70 at 1 s and 3.5 s per frame (live and after resume); two episodes count twice; multiple persons
+55 once; audio + integrity cumulative survives resume; Current Low / Cumulative 70 / Overall High / Final 70 through HTTP;
refresh + logout/login continue the session; suspended session finalised with cumulative; PROCTOR_DIAG suppression reasons.
**Before-check:** the 30 new tests were run against the ORIGINAL code: **22 failed, 8 passed**
(`beforecheck` run; only the new helper `core/json_safe.py` and the test assets were copied in, so the test files import).
- 15 failures reproduce a defect: NumPy bool in face output; frame/poll 500; proctor accepted as a student;
  mirrored upload; head direction labelled by the wrong axis; phone +100 instead of +70 (2 tests); persons +100
  instead of +55; audio/integrity missing from cumulative; refresh creates a new session; logout ends the exam; the
  real head-left turn; the mirrored real sequence; the real head-up timer; YAMNet speech not counted in cumulative.
- 7 failures are because a new field or method does not exist in the original: the new face-state fields,
  the calibration `reason`, `_head_quality`, `final_risk` in the stop response, the diag records, and `phone_trace`
  (2 real-phone tests).
- The 8 that passed are behaviour that was already correct and is left unchanged:
  - the conversion helper
  - poll scoping
  - latest-frame-wins preview
  - two separate phone episodes count twice
  - the tracker's operating point
  - iris gaze left/right (2 tests)
  - the downcast-eyes limitation

`tests/test_real_runtime_media.py` (9 tests, real MediaPipe / YOLOv8m / YAMNet on third-party media fetched by
`python tools/fetch_test_assets.py`; skipped — reported as not verified — when the files are missing): large head turn
left, mirrored input swaps to right, head up, iris gaze left and right, downcast eyes = closed (documented limitation),
a real phone is traced to the stage that stops it, phone-free photos (incl. a microphone, dark fabric, a statuette) are never CONFIRMED, YAMNet speech → `audio_speech`
event / typing → none.

## 23. Full test results

See the final section "Full regression — exact numbers" at the end of this report.

## 24. Performance

`benchmark/load_test_real_frames.py` — in-process (Flask test clients as browsers, no TCP/TLS), **real face frames**,
the page's server-driven pacing, real YOLOv8m + MediaPipe + YAMNet, 2 vCPU, detector pool 2, 40 s per level:

| Students | 1 | 5 | 10 | 20 | 30 |
|---|---|---|---|---|---|
| Listed in proctor poll | 1 | 5 | 10 | 20 | 30 |
| HTTP 5xx | 0 | 0 | 0 | 0 | 0 |
| Preview POST p50 / p95 ms | 2.1 / 2.8 | 1.7 / 5.4 | 1.7 / 8.0 | 3.0 / 12.4 | 4.1 / 19.2 |
| Snapshot GET p50 / p95 ms | 1.4 / 3.2 | 1.5 / 6.8 | 2.2 / 9.0 | 3.9 / 14.0 | 4.2 / 17.8 |
| Frame age at the proctor p50 / p95 ms | 33 / 66 | 31 / 64 | 35 / 66 | 52 / 98 | 78 / 146 |
| Proctor frames per student per s | 3.9 | 3.65 | 3.19 | 2.33 | 1.81 |
| Frames of the wrong student | 0 | 0 | 0 | 0 | 0 |
| AI frames analysed in 40 s (all students) | 50 | 78 | 60 | 43 | 39 |
| Median interval between analysed frames of one student | 0.8 s | 2.5 s | 6.7 s | 20 s | 40 s |
| AI time per frame (YOLOv8m ×2 scales + MediaPipe) ms | 775 | 1016 | 1348 | 1939 | 2043 |
| Students calibrated within 55 s (median time) | 1/1 (10.5 s) | 5/5 (17.3 s) | 10/10 (47.1 s, i.e. ≥ 45 s = the fallback path) | 0/20 | 0/30 |
| 4 s head/gaze rule and phone "2 obs in 4 s" feasible | yes | no (2.5 s/frame) | no | no | no |
| CPU avg (of 200 %) | 102 % | 180 % | 176 % | 181 % | 171 % |

**Defect found by this test and fixed:** the first run at 20 / 30 students (repaired tree before this fix — the original
code holds connections the same way but was not load-tested) failed — SQLAlchemy `QueuePool limit of
size 5 overflow 10 reached` → HTTP 500 on login and session start, only 15/20 and 16/30 students listed, preview
requests stuck for 30 s. Requests held their DB connection for the whole request (and logins during the deliberately
slow password hash). The connection is now returned right after authentication and before hashing; rerun: 0 errors,
30/30 listed.

Reading: live view, isolation, persistence and the dashboard hold up to 30 students here. **AI analysis does not:**
on 2 CPU cores YOLOv8m (two scales) + MediaPipe costs ≈ 0.8 s per frame, so beyond ~3–5 students the per-student
analysis interval exceeds what the temporal rules need. **30 students are NOT supported for AI detection on this
hardware** — size the server (GPU, or roughly one core per 1.2 analysed frames per second) or reduce the AI cost
(e.g. `PHONE_DETECTOR_STRATEGY=adaptive`, `DETECTOR_POOL_SIZE` = cores) and re-run the benchmark there.
Real browsers over Wi-Fi/TLS add network and decode time (not measured).
The run was made while the tried tracker change (§11) was in place; the frames contain no phone and no metric
in this table depends on the tracker's buffer arithmetic.

## 25. Items that require YOUR real webcam test

**Applying the repair.**
1. Unzip `exam_proctor_detection_fixes_repair_files.zip` over your `exam_proctor_detection_fixes` folder. It only
   adds or replaces the files listed in §20. Your `instance/` database, `models/` and recordings are not touched.
2. Start the server. On the first start, the nullable column `behavior_events.cumulative_points` is added
   automatically.
3. Optional: run `python tools\fetch_test_assets.py`, then `python -m pytest -q`.

`repair.patch` holds the same changes as a diff against your upload.

From the project folder, in PowerShell, with the Python you use for `run.py`:

```powershell
python tools\live_diag.py            # add --show for a preview window, --camera 1 for another camera
```

13 guided steps (neutral face, Head Left / Right / Up / Down, Eyes Left / Right / Up / Down, show phone, speak,
silence, second person). Each ends with **DETECTED / NOT DETECTED / SUPPRESSED — reason / MODEL MISS /
PIPELINE ERROR**, computed from the events the real pipeline emitted; nothing is marked successful automatically.
It writes `live_diag_report.json` — please send it back with the console output. It uses the same modules and the same
frame preparation as the exam page (raw 320×240 JPEG 0.65, one AI frame / 0.8 s, 16 kHz 1 s audio chunks).

Diagnostic mode for the real server:

```powershell
$env:PROCTOR_DIAG = "1"; python run.py
# optional: $env:PROCTOR_DIAG_FILE = "diag.jsonl"
```

prints one line per analysed frame per student (face, calibration, raw / neutral / corrected pose and gaze, direction,
orientation timer, phone stage, risk, last event, every suppression reason) and one line per audio window.

Needs your hardware: face detection in your lighting, the four head and gaze directions with your camera position,
your phone in front of your webcam, your microphone + YAMNet on Windows, live video between two real devices over your LAN.

## 26. Remaining limitations

1. Eyes Down (head still) is classified as closed eyes (§10); Eyes Up not verified.
2. Head Down not verified on a real head-down sequence (logic and sign verified).
3. **Phone detection remains weak (MODEL LIMITATION, §11):** real phones at the exam's 320×240 stop at the tracker's confidence gate (YOLO 0.2–0.5) and reach at most MONITOR; lowering the bar was measured to confirm a microphone, dark fabric and a cup. Fix = a phone model trained on webcam images (`training/`) or an operating point chosen on your own footage. Webcam accuracy NOT VERIFIED.
4. AI throughput: see 24 — beyond ~5 students on 2 cores the temporal rules cannot be met.
5. Live video is JPEG polling: ~4 fps tiles, ~6 fps zoom here; not 10–20 fps.
6. Audio thresholds uncalibrated (a cough was "speech"); whisper / shout not verified; continuous talking adds +20 per 10 s.
7. Browser integrity weights are applied as configured: one tab switch usually sends `tab_hidden` (+33) and `window_blur` (+22).
8. Calibration needs a frontal face (|pitch| ≤ 20°, |yaw| ≤ 15°); a camera that sees the face from far above/below falls back after 45 s.
9. One server process only (in-memory workers, event bus, detector pool) — unchanged design.
10. MediaPipe 1.1.0 (sandbox) can deadlock when a detector object is garbage-collected while another detector runs; the app keeps its detectors for the process lifetime, the new tests use one shared instance and close it explicitly. The original `test_real_mediapipe.py` creates and drops detectors and may be affected on 1.x; on the 0.10.x line pinned by `requirements.txt` this was not observed.
11. Windows, Python 3.10 and your installed package versions: NOT VERIFIED here (`live_diag.py` prints them).
12. The test suite has pre-existing cross-test pollution: the legacy `test_all.py::test_cross_student_isolation` uses a bare Flask app, so its background DB writer fails. This caused 1 intermittent failure in 3 full runs (see the last section). It does not affect `run.py`.

---------------------------------------------------------------------------------------------

## Final matrix

| Feature | Before | After | Proof |
|---|---|---|---|
| Correct project version | **FAIL** — your log ran `exam_proctor_latest_2026-09-14` | PASS — this report is about `exam_proctor_detection_fixes`; `run.py` prints the folder | log paths (0 × "detection_fixes"); start-up banner |
| /student/frame | **FAIL** 500 (`eyes_closed` numpy.bool_) | **PASS** 200 continuously | repro 200,200,500,500,500 → 5×200; `test_frame_and_poll_never_500_with_a_real_face` |
| /proctor/students/poll | **FAIL** 500 (proctor + admin) | **PASS** | same test; audit clean |
| Active student display | **FAIL** (0 Active) | **PASS** — tile after 0.95–1.4 s, 2 and 5 students all listed | Chromium e2e + multi-student |
| Live student video | **FAIL** — mirrored, only the 1st tile refreshed, zoom 0 fps offline | **PARTIAL** — all tiles 3.5–4.1 fps, frame age p50 ≤ 40 ms, zoom 5.9 fps; not 10–20 fps; real LAN devices NOT VERIFIED | Chromium measurements |
| Stream status | ERROR shown on failures ("Analysis: Server error") | **PASS** — Live → Reconnecting → Live 1.6 s after recovery | Chromium outage test |
| Face detection | not reproduced here (old-project message) | **PASS** on real photos (40/40); your webcam NOT VERIFIED | probe + diag fields |
| Head Left | **FAIL** (swapped; large turns ignored) | **PASS** (real frames, −37…−56°) / webcam NOT VERIFIED | `test_real_large_head_turn…`, browser mirror test |
| Head Right | **FAIL** (swapped) | **PASS** (real frames +29°) / webcam NOT VERIFIED | probe, mirror test |
| Head Up | **FAIL** on one real sequence (timer reset by gaze-label changes; another sequence reached 4 s) | **PASS** (both real sequences) / webcam NOT VERIFIED | `test_real_head_up`, `12b_…` |
| Head Down | swapped-axis not affected; large angles ignored | **PARTIAL** — logic & sign verified, no real head-down sequence | unit tests, 227-frame sign check |
| Gaze Left | **FAIL** (swapped) | **PASS** (real iris landmarks) / webcam NOT VERIFIED | `test_real_iris_gaze_left_right` |
| Gaze Right | **FAIL** (swapped) | **PASS** (real iris landmarks) / webcam NOT VERIFIED | same |
| Gaze Up | NOT VERIFIED | **NOT VERIFIED** (no real data) | — |
| Gaze Down | **FAIL** (eyes "closed") | **FAIL / LIMITATION** — documented, blendshape method identified, needs webcam data | `test_real_downcast_eyes…` |
| Phone | **FAIL** — real phones boxed by YOLO in most frames but stopped by the tracker's confidence gate (0/5 CONFIRMED, 2/5 MONITOR) | **FAIL / MODEL LIMITATION — unchanged on purpose**: the stopping stage is now reported per frame; a lower operating point was tried (3/5 CONFIRMED) but confirmed 2 of 82 phone-free photos and a cup → reverted; webcam NOT VERIFIED | `11_…`, `11b_…`, `test_real_phone_free_photos_never_confirm_a_phone` |
| Speech/YAMNet | not verified | **PASS** on real speech (0.97–1.00) and in Chromium end-to-end; whisper/shout NOT VERIFIED; Windows/TF NOT VERIFIED | probe, `test_real_yamnet…`, browser alerts |
| Multiple persons | +55 repeated with sparse frames / after resume | **PASS** — +55 once (live, sparse, resumed) | `test_multiple_persons_is_one_episode…` |
| Current Risk | PASS | **PASS** (decays to Low) | tests |
| Cumulative Risk | **FAIL** (reset on refresh/logout; audio/integrity missing; +70 repeated; resume drift) | **PASS** | table §16, tests |
| Final Risk = Cumulative | PARTIAL (finalised early on refresh/logout) | **PASS** | HTTP test, DB row, `/proctor/sessions` |
| Refresh persistence | **FAIL** (0.70 → 0.00) | **PASS** | test + probe |
| Reconnect | **FAIL** after logout; server restart inconsistent (0.00 → 0.33) | **PASS** (kill -9 + restart: 0.33 → 0.33, same session) | real `run.py` restart probe |
| 2 students | 2nd tile frozen | **PASS** (real Chromium, both tiles 4.0 fps) | browser_multi |
| 5 students | 4 tiles frozen | **PASS** for listing + live view (Chromium, 3.5–3.7 fps); one AI frame per student every 2.5 s here → temporal rules **FAIL** on this hardware | browser_multi + load test |
| 10 students | — | **PARTIAL** — 10/10 listed, 0 errors, live 3.2 fps; one AI frame per student every 6.7 s | load test |
| 20 students | **FAIL** in the first run of the repaired tree before the DB-pool fix (500s, 15/20 listed); original code not load-tested | **PARTIAL** — 20/20, 0 errors, live 2.3 fps; one AI frame per student every 20 s, no calibration | load test |
| 30 students | **FAIL** in the same first run (30 s stalls, 16/30 listed); original code not load-tested | **PARTIAL** — 30/30, 0 errors, live 1.8 fps, frame age p95 146 ms; AI detection not supported on 2 cores | load test |

---------------------------------------------------------------------------------------------

## Full regression — exact numbers

All runs used Python 3.11.15 on Linux with 2 vCPUs, `python -m pytest -q` on a fresh copy of the tree, the real
models, and the real-media assets present.

| Run | Code | Result |
|---|---|---|
| Baseline (before any change) | original `exam_proctor_detection_fixes` | **149 passed**, 0 failed, 1 warning — 268 s |
| Before-check of the 30 new tests | original code | **22 failed, 8 passed** (see §22) |
| final1, final2 | earlier repaired tree (with the tried tracker change, §11) | final1: 179 passed, 1 failed (intermittent, see below); final2: 180 passed |
| **final3 — the shipped tree** | repaired, `phone_tracker.py` = original | **179 passed, 0 failed, 0 skipped**, 1 warning — 289 s |
| of which: new `test_runtime_repairs.py` | shipped tree | 21 / 21 passed |
| of which: new `test_real_runtime_media.py` (real MediaPipe / YOLOv8m / YAMNet) | shipped tree | 9 / 9 passed |
| Guard check: same tests with the tried presence tracker | experiment only | `test_real_phone_free_photos_never_confirm_a_phone` and the tracker unit test **fail**, so the guards work (`11c_…`) |
| JS client test `node tests/js/test_client.js` | shipped tree | "proctor_client.js: all assertions passed" |
| `python -m compileall` | shipped tree | every project source compiles; the only error is in `evidence/repro_after.py` (see below) |

**How the totals add up:** 179 = 149 existing tests (all still pass, none modified) + 21 + 9 new tests.

**The one warning** is `PytestUnhandledThreadExceptionWarning` in the SSE pump thread of `test_real_mediapipe.py`.
It is identical in the baseline.

**The compileall error** is in `evidence/repro_after.py`, an **unchanged file from your upload**. It uses f-string quoting
that Python ≥ 3.12 accepts and 3.11 rejects, and it compiles on 3.13.

**The intermittent failure in final1** was `test_audio_events_propagate_end_to_end`. The background DB writer raised
"The current Flask app is not registered with this SQLAlchemy instance".
- It passed in 6 isolated reruns, in final2 and in final3.
- The legacy `test_all.py::test_cross_student_isolation` builds a bare `Flask(__name__)` app without the database.
  Run alone, its background writer logs this same error **78 times on the original code and 77 times on the repaired
  code**. This is pre-existing cross-test pollution: Flask-SQLAlchemy keys its shared session registry by
  `id(app_context)`, and a reused id can hand one test's session to another.
- It cannot occur in `run.py`, which runs exactly one app. It was left unchanged because fixing it means changing a
  test you did not ask to change.

**Measurements taken while the tried tracker change was in place:** the Chromium runs (§6, §13, §14, §19), the
load test (§24) and the `live_diag.py` replay. None of them used a phone image: the camera was a face photo and the
frames were face frames. The tracker's buffer arithmetic also affects none of the metrics reported from them.

**Not run here (NOT VERIFIED):**
- Windows / PowerShell
- your Python 3.10 and package versions
- your webcam, microphone and phone
- two physical devices over your LAN or HTTPS

`tools/live_diag.py` and `PROCTOR_DIAG=1` are provided for exactly these (§25).
