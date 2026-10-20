# FINAL HEAD / GAZE / LIVE VIDEO / EVIDENCE FIX — `exam_proctor_detection_fixes`

Phase 2, built on the phase-1 state (`FINAL_REAL_RUNTIME_REPAIR_REPORT.md`). Nothing was started over and no
older project was used. Phone, YAMNet, no-face, browser integrity, the risk model (current / cumulative / final,
LOW 0–29 / MEDIUM 30–59 / HIGH 60–100), session persistence, authorisation and multi-student isolation are
unchanged unless a section below says otherwise and shows the evidence.

Labels used: **PASS** (shown here on real media / a real browser), **PARTIAL**, **FAIL**,
**NOT VERIFIED ON USER HARDWARE** (needs your webcam). "Real log" = the log you sent (`17:24:02–17:27:34`,
one student, admin test session, 217 AI frames). "Recording" = your earlier 172 s webcam recording that was
already in the project (`static/recordings/…`). I used it **for local analysis only**; it and every image derived
from it are excluded from the delivery. Test machine: 2 CPU cores, no GPU, with Chromium, the server and the
"student" all on one machine.

---

## 1. Why each HEAD direction did / did not emit in your real log

Times are seconds after the first AI frame. Every line comes from the `[DIAG …]` records in your log.

| Direction | What the log shows | Why | Stage that failed |
|---|---|---|---|
| **Right** | Emitted twice: held 4.2 s (76.3→80.7 s) and 4.1 s (146.8→150.8 s). The second turn produced a **second row and a second screenshot** at 12.4 s (159.1 s, "same episode continues: new event row after cooldown"). | Classification and timing worked. The duplicate came from the 8 s event cooldown re-opening a row while the same turn continued. | Event creation (duplicate) |
| **Left** | Never emitted. Turns at 70.7→73.9 s (yaw −54…−64°) measured **3.2 s**, then the next frame was already a right turn. Turns at 110.4→113.8 s measured 1.7 s, then the episode reset. | AI frames arrived about every 0.8–1.0 s, and the hold is measured from the first frame that saw the turn to the last one. A ~4 s hold therefore measures about 3.2 s. My replay of the recording shows the same: 1.25 Hz measured 3.2 s for episodes that 4 Hz measured at 4.1 s. | Sampling rate → temporal duration |
| **Up** | 91.8 s: pitch **+52.5°** (corrected), but `face_too_small` (face box 3.4 % of the frame). Head pose was invalid. One frame later it was valid for a single frame, then gone. | The 4 % face-size floor of the gaze quality gate was also applied to head pose. A head tilted back shrinks the face box. | Raw detection (validity gate) |
| **Down** | 161.2→162.4 s only: one 1.1 s episode, then back to normal at 166.6 s. | In this log the AI never saw a sustained head-down (≥ 4 s beyond −12°). No code fault is visible for Down here. On the recording, head-down episodes were measured (see §8). | — (not sustained in the log) |
| **Full profile** | 97.0→99.7 s: 4 frames with `face n=1 lm=0`, i.e. a face was found but no landmarks. Head direction was unknown. | At about 90° the landmark model returns nothing, so no direction existed (also visible in your "head turn" screenshot). | Raw detection (landmarks) |

## 2. Why each GAZE direction did / did not emit

Of 209 real-log frames with a face, gaze was **valid in only 40 (19 %)**:

| Label | Frames |
|---|---|
| `Unknown` | 100 (48 %) |
| `Eyes Closed` | 69 (33 %) |
| `Looking Center` | 32 |
| `Looking Left` | 7 |
| `Looking Right` | 1 |
| `Looking Up` / `Looking Down` | 0 |

| Direction | What happened | Why |
|---|---|---|
| **Left** | Held 3.2 s (181.3→184.5 s), then one frame read "Looking Right". No event. | The same ~1 Hz under-measurement as head-left. |
| **Right** | One frame only. | Never sustained per the AI. |
| **Up** | Never classified. | Vertical gaze came from the iris/lid ratio, which barely moves when the eyes roll up (your "eyes up" screenshot). |
| **Down** | Shown as **"Eyes Closed"** (69 frames). | The old lid-ratio rule (`opening < 0.55 × neutral opening`) cannot separate lowered lids from a blink. The neutral opening from the calibration fallback was also inflated. A gaze-down event was therefore impossible. |

## 3. Actual AI FPS

| | Head / gaze (face) | YOLO (phone / persons) |
|---|---|---|
| Real log (old) | Median **1.06 fps** (0.94–1.27), on the same frame as YOLO | same |
| Real log, exam tab hidden (106.6–196 s) | 0.94–0.97 fps (browser 1-second timer clamp) | same |
| **Now**, 1 student (this 2-core machine, measured on the server) | **3.0 fps** (fast face path, `face_ms` 333) | **1.05–1.27 fps** (unchanged cadence, `ai_ms` 800) |
| Now, 5 / 10 / 20 / 30 students (load test, 2 cores) | 2.9 / 2.1 / 0.7 / 0.4 fps per student | 0.3 / 0.1 / ~0.03 / ~0.03 fps per student |

How it works now:
- The browser uploads an AI frame every `face_ms` (333 ms for ≤ 10 students, 800 ms for 11–20, 1000 ms above that).
- MediaPipe (≈15–20 ms) analyses every one of them on its own thread (`core/student_worker.run_face_once`, `FACE_FAST_THREADS`, default 1).
- YOLO (≈660 ms on 2 cores) runs at most every `ai_ms` on the newest frame.
- Head / gaze never wait for YOLO. This is proven by `test_fast_face_path_does_not_wait_for_yolo`: ≥ 6 face analyses happen while one 2 s YOLO frame is still running.

## 4. Actual temporal timing behaviour

- **Threshold:** the 4.0 s threshold (`ORIENTATION_MIN_SECS`) was **not** changed.
- **Episode duration:** monotonic time from the first analysed frame that showed the deviation.
  - Up to 2 s of invalid frames is tolerated.
  - A blink counts as an invalid frame, so it no longer resets an episode.
  - A "lowered eyes" episode is back-dated to when the eyes went down.
- **Measurement lag:** at 3 Hz the measured hold lags the real hold by ≤ 0.33 s. The event is created when the real hold is about **4.0–4.4 s**.
  - Real browser, your recording, three runs: the event appeared in the proctor's log at 98.8–99.3 s ("held 4.0–4.3 s"); in the first run the head was first seen turned right at 94.9 s.
  - Before, at ~1 Hz, the lag was up to ~1 s, which is why 4 s holds were missed.
- **Brief movements:** 0.3–1 s (and up to 3.9 s) movements create **no** event, image or risk.
  - Tests: `test_brief_head_movements_never_create_evidence` (8 glances).
  - Real log: every brief turn above ended "< 4 s (brief movement: no event)".
- **One episode = one row:**
  - A continuing episode stays **one event row**: the repeat count rises and the description carries the running duration, for example "for 12.3s".
  - It adds +0 points and keeps **one image**. It no longer opens a second row after the 8 s cooldown.
  - The existing one-time "persistent" award at 15 s (+15 %) is kept, as the risk policy requires. It is its own row but re-uses the episode's image.
- **New episode:** after returning to normal (≥ 2 normal frames and > 2.5 s gap), a new turn creates a new row, a new image and its own one-time points.
  - Test: `test_head_turn_episode_gives_one_event_and_one_clean_evidence_frame`.

## 5–12. Results per direction

Direction is always from the **student's** point of view. Frames reach the AI raw, not mirrored, as fixed in phase 1. "Your frames" below are your 5 screenshots, analysed as raw camera frames after calibrating on your recording. The student-view screenshots are mirrored, so they were flipped back first.

| # | Direction | Evidence now | Status |
|---|---|---|---|
| 5 | **Head Left** | Real 3DDFA head-turn video (yaw −37…−56°): `head_deviation left` ≥ 4 s (`test_real_large_head_turn_to_the_left…`). Mirrored input swaps L/R (test). Your frame u5 (raw): **Head Left**, yaw −57°. Full profile to the left: new detector-keypoint fallback (§ below). Real-log failure was timing: fixed by the 3 Hz face path. | PASS on real media · **NOT VERIFIED ON USER HARDWARE** |
| 6 | **Head Right** | Real browser + your recording (3 runs): **confirmed at 4.0–4.3 s held, one row, one image** that shows your head turned to your right. Server replay: 5.7–6.0 s episode, one row. Your frame u2: **Head Right** (yaw +40°). Your profile frame u3 (raw): **Head Right** via the new profile fallback (before: no direction). | PASS on your recording · **NOT VERIFIED ON USER HARDWARE** (live) |
| 7 | **Head Up** | Head-specific size floor (2 % / 32 px on the landmark box). Real-image test `test_real_small_face_keeps_a_usable_head_pose` (3 real faces shrunk to 3.1–3.7 % of 640×480: still "poor" for gaze but usable for head, pose within 3° of full size). Real head-up sequence test (`test_real_head_up`). Your frame u4 as captured: **Head Up**. Mirrored + JPEG-compressed, the landmark model returned no landmarks: an extreme tilt (≈ +50°) is at the model's limit. | PASS (real media) · PARTIAL for extreme tilt · **NOT VERIFIED ON USER HARDWARE** |
| 8 | **Head Down** | Server replay of your recording: "Head tilted down" **12.3 s** (one row, ×25 repeats, one image) and **5.0 / 7.3 s**. The calibration fallback bug that made every normal frame "Head Down" is fixed: on your recording the neutral pitch was +19.6°, now −0.2° (§ blink/calibration). | PASS on your recording · **NOT VERIFIED ON USER HARDWARE** |
| 9 | **Gaze Left** | Real photos (same person looking straight / to her left): `test_real_iris_gaze_left_right[img4]` → `Looking Left`, `eye_deviation` ≥ 4 s. Real-log failure was timing (3.2 s measured): fixed by the 3 Hz face path. | PASS on real media · **NOT VERIFIED ON USER HARDWARE** |
| 10 | **Gaze Right** | Same test with `img1` → `Looking Right`. Your frame u1 (eyes up and to the right): **`eye_deviation right`**. | PASS on real media · **NOT VERIFIED ON USER HARDWARE** |
| 11 | **Gaze Up** | Now from MediaPipe's trained `eyeLookUp` blendshape relative to the student's own neutral value (+0.22). Your frame u1: eyeLookUp **0.29 vs neutral 0.01**, so the upward look is measured. Its label is **Right**, because the sideways component is larger (largest-exceedance rule); it is still a confirmed eye deviation. A purely upward look was not in your material. | PARTIAL · **NOT VERIFIED ON USER HARDWARE** |
| 12 | **Gaze Down** | Separate from blink (§13). Eyes that look closed for more than a blink (≥ 1.0 s) with `eyeLookDown` ≥ neutral + 0.30 become **Looking Down**, which is valid and starts a down episode back-dated to when the eyes went down. Real frames (`headpose_demo.gif`): `test_real_blink_is_not_looking_down_but_sustained_lowered_eyes_are`. **Limitation for you:** in your recording your neutral eyeLookDown is already 0.43–0.52 (reading a screen below the camera) and looking down reached only 0.51–0.58 (+0.30 needed), so eyes-only down is mostly **not** detectable for you. Head down plus eyes down is (combined deviation, below). | PARTIAL · **NOT VERIFIED ON USER HARDWARE** |

**Policy change (required behaviour):**
- Before: head down and eyes down together were called `reading_down` and never became an event.
- Now: this is `combined_deviation` (looking below the screen: lap, desk or phone) and becomes an event after 4 s.
- Head and eyes in **opposite** directions (head down, eyes up, i.e. still reading the screen) remain `ambiguous` and never become an event.

**New: full profile.**
- The problem: when a face is found but the landmark model returns nothing (about 90°), there was no head direction at all.
- The fallback: the face detector's own keypoints are used, **only when the landmarks failed**. A full profile is assumed when the eye-to-eye distance is ≤ 0.20 of the box width and the nose offset is ≥ 0.40.
- Measured on your frames:

| Pose | Eye span | Nose offset |
|---|---|---|
| Frontal | 0.39–0.43 | ≤ 0.15 |
| 40–45° turn (landmarks still work) | 0.22–0.33 | 0.35–0.43 |
| Full profile | 0.06 | 0.47 |

- Replayed over your whole 172 s recording it fired on 1 frame (a brief left turn, no event) and changed no episode.

**Cadence:** the 3 Hz face path fixes the timing failures of Head Left and Gaze Left in your log.

## 13. Blink vs gaze-down behaviour

There are three separate states, reported as `eye_state` (`open` / `closed` / `lowered`) to the proctor and to `PROCTOR_DIAG`.

- **BLINK (`Eyes Closed`):** `eyeBlink` ≥ max(0.55, the student's neutral eyeBlink + 0.20).
  - Lasts < 1 s, has no gaze direction and does **not** reset an orientation episode (treated as an invalid frame).
  - Measured on 8 real blinks in your recording:

| Rule | False "closed" frames | Blinks caught |
|---|---|---|
| Old lid geometry (ideal neutral) | 5.7 % | 8/8 |
| `eyeBlink` ≥ 0.55 | 2.1 % | 8/8 |
| `eyeBlink` ≥ neutral + 0.25 | 0 % | 8/8 |

  - Real blinks scored eyeBlink 0.60–0.71.
  - On the whole recording, `Eyes Closed` fell from **2.7–4.9 % → 0.7–1.1 %** of calibrated frames.
  - False geometric `Looking Down` fell from **56 of 154 frames → 1**.
- **LOOKING DOWN:** closed-looking ≥ 1.0 s with `eyeLookDown` ≥ neutral + 0.30.
- **LOOKING UP:** `eyeLookUp` ≥ neutral + 0.22.
- Thresholds can be overridden with `GAZE_BLINK_CLOSED`, `GAZE_BS_UP_DELTA` and `GAZE_BS_DOWN_DELTA`.
- **Calibration (the root of the inflated neutral):**
  - The fallback after 45 s now uses the **pose held most of the time** (the densest pose cluster within 4°), not the samples taken after the last reset. On your recording this changes the neutral pitch from +19.6° to −0.2°.
  - It can also use head-usable frames whose gaze was too weak for strict calibration.
  - It keeps collecting a strict calibration in the background and replaces the fallback when one completes ("strict (replaced fallback)").
  - Test: `test_fallback_calibration_uses_the_densest_pose_cluster`.

## 14. What the student can see

**Only:**
- the exam
- their own camera preview
- the timer
- connection notices
- **Stream: Live**, **Proctoring: Connected**, **Microphone: On**

**Removed from the page:**
- risk card, peak risk and events tiles
- head / gaze / orientation / phone / face / audio labels
- violation toasts
- the final-risk summary

**The student APIs return no detection data:**

| Endpoint | Returns |
|---|---|
| `/student/frame` | `{active, stream (technical), server_ts, pace, ack}` |
| `/student/status` | session id, room and technical stream state |
| `/api/sessions` | the student's sessions; for a **running** one, `total_events`, risk and label are `null` (they rose with every confirmed violation — found by the verification) |
| `/student/events` | `{active}` only |
| `/student/integrity` | `{"status": "ok"}` |
| `/student/session/stop` | no final risk |
| `/api/events`, `/api/export/csv`, `/stats/summary`, reports | the student's **finished** sessions only |

- **Legacy MJPEG feed:** `/video_feed` now serves a student only the raw camera preview. Before, it could serve the AI snapshot, which carries the HUD with head / gaze / risk.
- **Real browser (separate cookie jars), your recording as camera:**
  - For 115 s the student page's visible text never contained risk / gaze / looking / head / phone / violation / suspicious / orientation / confidence / detected.
  - The same held on 2 and 5 student pages.
  - Tests: `test_student_page_and_api_reveal_no_detection`, plus requirement-driven test updates (§24).

## 15. What the proctor can see

- **Detail view of the selected student:**
  - Live video at the student's full send rate, with the line `stream: live · 15.1 fps · capture→display 19 ms`.
  - The student browser's own numbers (send fps, encode ms, upload ms), or **"student exam tab HIDDEN: the browser sends at most ~1 fps"**.
- **Current detector state** ("live — not a violation until confirmed in the Event Log"):
  - **Current gaze**, **Current head**, Faces, Audio.
  - The orientation line, for example `head deviation right · held 3.0 s (recorded as a violation at 4 s)`.
  - It refreshes twice a second.
- **Unambiguous risk labels:**
  - Pill: **Overall: High**.
  - Line: **Current: 65% High · Cumulative: 100% High · …**.
  - Gauge: "Cumulative risk (= final risk)".
- **Event Log — confirmed violations** (with an *evidence* link per row) and the room alert feed.
  - Real browser: `Orientation: head_deviation (right) for 4.3s — Head turned right · evidence` (4.0–4.3 s over three runs) appeared in both within 0.5 s of confirmation.

## 16. Evidence screenshot implementation

- **When:**
  - Exactly when a violation is **confirmed** (the row is created), never per frame and never before confirmation.
  - Tests: no file exists after 3.9 s of a turn; exactly 1 file after confirmation; still 1 after 13.6 s; a new turn gives a 2nd file.
- **Which image:**
  - The analysed camera frame that confirmed it: the un-annotated copy kept before any drawing, JPEG q85.
  - **No detector text is burned in.** Before, the label was drawn on the image.
  - Test: the stored image equals the camera frame (mean difference < 4 grey levels), although the AI snapshot got a HUD.
  - Audio and browser events use the newest raw preview frame.
- **Linked data:** the `behavior_events` row holds `id`, `session_id`, `student_id`, `room_id`, `event_type`, `description` (state, direction, running duration), `timestamp`, `confidence`, `cumulative_points` (risk added), `repeat_count`, `source` and `screenshot_path`. The file name holds the student id, session, timestamp and type.
- **One per episode:** the persistent-tier row re-uses the image (`test_long_episode_persistent_tier_reuses_the_episode_image`).
- **Access** (`/static/violations/<file>`):

| Who | During the exam | After the exam |
|---|---|---|
| Admin | allowed | allowed |
| Proctor / instructor who owns the room | allowed | allowed |
| The student, own images | **403** | allowed |
| Other proctors and students | 403 | 403 |
| Anonymous | redirect to login | redirect to login |

  - Path traversal is refused.
  - **Static-path bypass (found by the independent verification, already in phase 1, now fixed):**
    - Flask's built-in `/static/<path>` handler normalises the path. So `/static/./violations/<file>`, `/static/css/../violations/<file>` and `/static/%2e/violations/<file>` (and on Windows `/static/Violations/…`) never reached the protected route.
    - They served the evidence JPEG, and the same way recordings, to **anyone without login** (verified with raw HTTP on a real server: 200).
    - Every static request that resolves inside the evidence or recordings folder is now handed to the protected view. All variants now give 302 (login) for anonymous and 200 for the room's proctor. For **evidence** they give 403 to the student during the exam, and to other students and proctors. For **recordings** the existing policy is unchanged: the student may open his own recording; others get 403.
    - Test: `test_static_path_variants_cannot_bypass_evidence_protection`. It fails on the phase-1 code and passes now.
  - Evidence of browser / audio events is the raw camera preview, or the newest raw AI upload. It is **never** the AI snapshot with the detector HUD; this fallback was also found by the verification (test `test_browser_event_evidence_is_a_raw_camera_image_never_the_hud`).
  - Real browser: student 403 during the exam, proctor 200, student 200 after the exam.

## 17. Report implementation

- **New "Confirmed violations" section** (HTML, PDF and CSV columns), proctor / admin, and the student after the exam.
  - One row per confirmed episode in time order.
  - Columns: `#`, clock time and offset from exam start, human-readable name (the dashboard's labels), details (for example "Head turned right", "Eyes looking down", "Phone confirmed …"), **direction**, **duration** (head / gaze / no-face), confidence, **risk added** and the **evidence thumbnail**.
  - The thumbnail opens the full image; the PDF embeds it.
  - "+0" rows say why: "same episode" or "cumulative already 100%".
  - Covers phone, suspected phone, multiple persons, no face, head, gaze, audio and browser integrity. The existing evidence gallery, video player, timeline and log are kept.
  - The CSV gets new columns (Violation, Direction, Duration, Risk added, Repeats) and formula-injection protection on the description.
- **Data source:** `routes/api_reports.py` now passes `id`, `seq`, `cumulative_points`, `repeat_count` and `source` for each event.
- **Tests:** `test_report_lists_confirmed_violations_with_evidence` (HTML / PDF / CSV, images load for the proctor, another proctor is refused, the student is refused during the exam) and `test_confirmed_violations_parsing`.
- **Real browser:** after the exam the proctor's report showed every confirmed row with its image loaded (320×240): 6, 4 and 5 rows in three runs; final run: suspected phone, phone, Head Right held 6.0 s. The student received 200 for his own report.

## 18. Live-video bottleneck

1. **Your log (preview ~13 → ~1 fps).**
   - The student's exam tab was **hidden**: `integrity_tab_hidden` at 106.6 s, `window_focus` at 196.1 s.
   - Chrome runs the timers of a hidden tab at most once per second. Preview fell to exactly **1.0 / 0.9 fps** from about 121 s (the server's rate meter averages over a window) until the tab came back. The AI uploads fell from 1.07–1.24 to 0.94–0.97 fps at the same moment.
   - During 0–40 s the *proctor* tab was the throttled one: `/proctor/streams` and snapshot requests ran at exactly 1 per second. During 40–100 s the dashboard sent nothing at all. You were switching tabs in one window, so one of the two pages was always throttled.
   - This is the browser, not the server, and a student hiding the tab is already a `tab_hidden` violation.
   - **For a one-laptop test:** put the student and the proctor in **two separate windows side by side** (both visible), or use two devices. The proctor view now names this case ("student exam tab HIDDEN").
2. **Detail view: backdrop blur.**
   - A full-screen `backdrop-filter: blur()` behind the detail modal, over a dashboard that keeps animating (a pulsing badge), was recomputed every frame. It cost about **1 CPU core** in Chromium.
   - On one machine it starved the student page (student uploads 15 → ~7 fps), so the selected student showed 5–7 fps.
   - Removed for the live-video modal only (a slightly darker solid overlay instead).
3. **Detail view: 150 ms polling timer.** It capped the display at 6.7 fps, re-sent the frame already on screen (304s), and showed frames ~50 ms old on average. It was replaced by a **long-poll that answers the moment a newer frame exists**: one request per frame, latest frame wins, no queue.

## 19–21. Preview FPS, frame age, selected-student FPS — before → after

Same test before and after: real Chromium, proctor and student in separate contexts on the same 2-core machine, fake 30 fps camera, 15 s per phase. "Before" = the phase-1 code (`video_bench.py`).

| Selected student (detail view) | Before | After |
|---|---|---|
| Displayed fps | **4.73** | **15.1** |
| Display gap p50 / p95 / max | 186 / 396 / 528 ms | **66 / 83 / 125 ms** |
| Frame age when served p50 / p95 | 51 / 185 ms | **1 / 5 ms** |
| Capture → arrival in proctor page p50 / p95 | not measurable (no capture time) | **19 / 37 ms** (includes the student's JPEG encode) |
| Snapshot requests/s (304 = re-sent nothing) | 9.59 (16 × 304) | 15.03 (0 × 304; every request is a new frame) |
| Student's own preview upload | 6.87 fps, p95 upload 228.5 ms | **15.1 fps**, p95 24 ms |
| Grid tiles | 4.0 fps | 4.0 fps (unchanged design; paused while the detail is open) |

- **Proctor on a separate device** (student = simulated device):
  - Before: 6.65 fps.
  - After: **15.12 fps**, capture→arrival **7 / 14 ms**.
- **Latency target** (median < 100 ms, p95 < 200 ms): **met** (19 / 37 ms single machine; 7 / 14 ms separate device).
- **Real browsers:**

| Students (real Chromium pages) | Selected student | Capture → display |
|---|---|---|
| 2 (2 runs) | 15.4–15.5 fps | 26–28 ms |
| 5 (6 Chromium camera pages + server on 2 cores; CPU-bound, not a protocol limit) | 6.6 fps | 183 ms |

- **Selected-student priority** (side-channel, `WATCHED_PREVIEW_PRIORITY=0` turns it off): in a class of > 10 students a student reading the raw upload responses (browser dev tools) can see `preview_ms` drop to 66 ms while he is being watched.
  - While a proctor has a student's detail open, that student's browser is told to preview at 66 ms (15 fps) whatever the class size; the rest of the class keeps its tier.
  - 12 students (simulated devices): class tier ~9–10 fps, selected student **14.5 fps**, 28 / 86 ms.
- **What each change gave** (ablation, "revert if no benefit"), all kept:

| Change | Measured effect |
|---|---|
| No blur | Student preview 6.9 → 15 fps; browser CPU 133 → 76 %. |
| Long-poll | Display 6.6 → 14.6 fps; age 32 → 1 ms. |
| Grid pause | −4 invisible tile requests/s. |
| Watched priority | 9–10 → 14.5 fps at 12 students. |

  The 500 ms detail status refresh is a functional requirement (current head / gaze); it costs 2 small requests/s.
- **MJPEG / WebSocket / WebRTC:** not needed. The HTTP long-poll reaches the student's send rate with ≤ 37 ms p95.

## 22. CPU impact

| | Before | After |
|---|---|---|
| Browsers (proctor + student, detail open, one machine) | 133 % | **84 %** |
| Server, 1 student, grid | 87 % | 88 % |
| Server, detail | 64 % | 83 % (it now receives twice as many preview frames, plus the face path: 3 × ~17 ms/s) |

Several students on **2 cores**:
- The face path takes a share YOLO had.
- Per-student YOLO interval: 5 students 2.5 → 3.3 s; 10 students 6.7 → 10 s.
- Head / gaze interval at 10 students: 6.7 s → **0.5 s**.
- Calibration completes for 20/20 and 30/30 students (was 0/20, 0/30).
- At 20 students the YOLO interval went from 20 s to ≥ 30 s; 30 s is the whole measuring window, so at most one YOLO frame per student.
- Preview POST p95 rose under load:

| Students | Phase 1 | Phase 2 |
|---|---|---|
| 10 | 8.0 ms | 12.5 ms |
| 20 | 12.4 ms | 23.5 ms |
| 30 | 19.2 ms | 30.5 ms |

  The face analyses share the 2 cores.
- The phone rule "2 observations in 4 s" was already infeasible at ≥ 5 students on this 2-core machine in phase 1.
- For 1 student (your test) YOLO cadence is unchanged.
- `FACE_FAST_THREADS=0` restores the previous single path exactly.

Load test (`benchmark/load_test_real_frames.py`, real frames, real models, 2 cores):

| Students | Head/gaze fps per student | Head/gaze interval | Calibrated | Orientation 4 s rule feasible | Preview POST p95 | Frame age p50/p95 | 5xx | Wrong-student frames |
|---|---|---|---|---|---|---|---|---|
| 1 | 3.0 | 0.3 s | 1/1 | yes | 3.1 ms | 34/67 ms | 0 | 0 |
| 5 | 2.9 | 0.3 s | 5/5 | yes (was no) | 6.7 ms | 35/66 ms | 0 | 0 |
| 10 | 2.1 | 0.5 s | 10/10 | yes (was no) | 12.5 ms | 35/68 ms | 0 | 0 |
| 20 | 0.7 | 1.5 s | **20/20** (was 0/20) | no (2 cores) | 23.5 ms | 52/102 ms | 0 | 0 |
| 30 | 0.4 | 2.3 s | **30/30** (was 0/30) | no (2 cores) | 30.5 ms | 75/147 ms | 0 | 0 |

## Real test matrix (32 items)

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Neutral head | PASS | Recording through server + browser: calibration (fallback ≈ 45 s, densest pose), "no sustained head / gaze deviation", no event |
| 2 | Head Left sustained | PASS (real media) | 3DDFA head turn −37…−56° → event ≥ 4 s; your frame u5 (raw) → Head Left |
| 3 | Return neutral | PASS | Head/gaze returns to Normal (browser timeline); new episode only after return (test) |
| 4 | Head Right sustained | PASS (your recording, real browser) | Event at 4.0–4.3 s held (3 runs), 1 row, 1 image |
| 5 | Return neutral | PASS | As 3 |
| 6 | Head Up sustained | PASS (real media), PARTIAL for extreme tilt | `test_real_head_up`, small-face test, your u4 |
| 7 | Return neutral | PASS | Tests |
| 8 | Head Down sustained | PASS (your recording) | 12.3 s and 5.0 / 7.3 s episodes, 1 row each |
| 9 | Brief Head Left → no violation | PASS | Browser: brief left at 64.0–64.5 s (3 runs), no event; `test_brief_head_movements_never_create_evidence` |
| 10 | Eyes Left sustained | PASS (real photos) | `test_real_iris_gaze_left_right[img4]` |
| 11 | Eyes Right sustained | PASS (real photos) | `[img1]`; your u1 → eye deviation right |
| 12 | Eyes Up sustained | PARTIAL | Blendshape up measured on your u1 (0.29 vs 0.01); label = larger sideways component |
| 13 | Eyes Down sustained | PARTIAL | Real GIF test passes; weak for your eyes (neutral eyeLookDown high) |
| 14 | Blink → not gaze-down | PASS | Real-frame test; recording: 8/8 blinks, false closed 2.7–4.9 % → 0.7–1.1 % |
| 15 | Brief eye glance → no violation | PASS | Tests; real log (3.2 s left glance → nothing) |
| 16 | Phone | PASS (unchanged) | Your recording via server: "Phone confirmed … (72–80 %)" + evidence; real-YOLO phone tests |
| 17 | Speech | PASS (unchanged) | YAMNet real-audio tests (`speech_jfk.flac`); not part of the browser runs (silent microphone) |
| 18 | No face | PASS (unchanged) | Tests (5 s grace, brief vs persistent) |
| 19 | Second person | PASS / PARTIAL | Real-YOLO two-person photo; consecutive-frame rule; arm-with-phone limitation |
| 20 | Tab switch | PASS (unchanged) | Your real log (`integrity_tab_hidden`); integrity tests |
| 21 | Focus loss | PASS (unchanged) | Your real log (`window_blur` / `focus`); tests |
| 22 | Fullscreen exit | PASS (unchanged) | Your real log (`fullscreen_exit`); tests |
| 23 | Cumulative persistence | PASS (unchanged) | Never decreases, survives resume (tests) |
| 24 | Report evidence | PASS | Browser + `test_report_lists_confirmed_violations_with_evidence` |
| 25 | Student UI hides orientation | PASS | Real browser 115 s; 2 and 5 student pages; API tests |
| 26 | Proctor UI shows current Head / Gaze | PASS | Real browser timeline (Head Right, "held 1.0…4.3 s" up to the event) |
| 27 | Confirmed orientation in report | PASS | Real browser report row "Head turned right · right · 6.0 s" (5.7 s in the first run) + image |
| 28 | Confirmed visual event has evidence | PASS | Phone / persons / orientation / no-face rows (tests, browser, replay) |
| 29 | Live preview, one student | PASS | 15.1 fps, capture→arrival 19 / 37 ms |
| 30 | Selected detail view | PASS | 15.1 fps (was 4.73) |
| 31 | 2 students | PASS | Real browsers (2 runs): 2 tiles, detail 15.4–15.5 fps, 26–28 ms |
| 32 | 5 students | PARTIAL | Real browsers on one 2-core machine: works, detail 6.6 fps / 183 ms (CPU-bound) |

The whole matrix on **your webcam** remains **NOT VERIFIED ON USER HARDWARE**.

**Screenshot test (explicit):**

| Requirement | Result |
|---|---|
| Before a head / gaze event is confirmed (turn held 3.9 s) | **no evidence file** |
| After confirmation | **exactly one** file, which is the evidence of that row |
| Same episode continued to 13.6 s | still one file |
| New episode | a second file |
| Report | shows that file in the row |
| Student, during the exam | **403** (route and report) |
| Proctor of the room / admin | **200** |
| Another proctor | 403 |

Tests and the real browser run both confirm these.

## Other finding: false "Multiple persons" (+55 → HIGH) from a single YOLO frame

Replaying your 172 s recording through the server at its real cadence (one person on camera) produced **two** "Multiple persons (2)" events (+55 each):
- **One** from a whole-frame box nested around you.
- **One** from your arm holding the phone.

Each came from a **single** YOLO frame (2 of 194). Offline at 4 Hz, 7 of 641 frames had 2 persons and all were isolated.
- **Fix:** a second person must be seen on **2 consecutive YOLO frames** (`MULTI_PERSON_CONFIRM_FRAMES`, 1 = old behaviour).
- **Result:** the isolated false event is gone. Test: `test_second_person_needs_consecutive_detector_frames`. The real-YOLO two-person photo test still passes.
- **Remaining (PARTIAL):** while a phone is held up next to the face, YOLO can count the arm as a person on consecutive frames. One such event remained in the replay. The phone itself is correctly confirmed in the same moment. The detector (`phone_detector.py`) was not changed.

## Intermittent lost event row (found by the full regression, fixed)

`tests/test_audio_pipeline.py::test_audio_events_propagate_end_to_end` failed in 2 of 3 full runs. It also failed on the **phase-1 tree** (1 of 3 runs in the same configuration), so it is not new.

**Root cause:**
- `test_all.py` runs its checks at import and gives `StudentWorker`s a bare `Flask()` app that Flask-SQLAlchemy is not initialised on. Their snapshot jobs fail in the single DB-writer thread.
- Flask-SQLAlchemy removes the scoped session only in the teardown of apps it was initialised on. So the **broken session stayed registered under `id(app context)`**.
- When a later job's app context got the same id (memory reuse), it received that session, and its `behavior_events` row was lost (`PendingRollbackError`).

**Fix:** every DB job now runs in `StudentWorker._db_context()`, which always calls `db.session.remove()`.

**Before → after:**
- Running only that test with the full collection: 5 of 6 failed before, 4 of 4 passed after.
- `test_failed_db_job_never_leaves_a_stale_session` fails on the phase-1 code and passes now.

## 23. Every file changed (vs phase 1)

| File | Why |
|---|---|
| `modules/detection/face_analyzer.py` | Eye blendshapes (blink / up / down / left / right) relative to the student's neutral values. Blink vs lowered eyes vs looking up. Head-specific size floor (Head Up). Mode-seeking fallback calibration plus strict upgrade. Blink-tolerant orientation episodes. `combined_deviation` for head+eyes down. Full-profile fallback. New output fields (`eye_state`, `head_source`, …). |
| `core/student_worker.py` | Fast face path (`run_face_once`). YOLO gated by `ai_ms`. A continuing face episode is coalesced (one row, running duration). Evidence = clean frame. Persons need 2 consecutive frames. Long-poll frame wait. Watched flag. Browser upload stats. Raw-preview accessor. DB jobs always release their session (`_db_context`). The YOLO-only evaluation no longer touches the no-face timer. Evidence fallback = raw AI upload, never the HUD snapshot. |
| `core/detector_pool.py` | Separate FaceAnalyzers for the face path (`acquire_face`). |
| `core/ai_scheduler.py` | Generic scheduler (used for the face path too). |
| `core/session_manager.py` | Face scheduler. Per-student `pace(student_id)` (selected-student priority, `WATCHED_PREVIEW_PRIORITY`). Stats pass-through. |
| `core/pacing.py` | `face_ms` tiers. `WATCHED_PREVIEW_MS`. |
| `core/event_log.py` | Replace the description on coalesced repeats. |
| `core/risk.py` | Persistent-tier rows re-use the episode image (`EVIDENCE_TYPES`). Weights / thresholds unchanged. |
| `core/diag.py` | Path tag (F / Y), face fps, eye values, head source, browser stats in `[DIAG]`. |
| `routes/api_student.py` | Student payloads without detection / risk. `X-Client-Stats` (whitelisted). Per-student pace. |
| `routes/api_proctor.py` | Long-poll snapshot (`after` / `wait`, capture-time header). `face_fps`. Watched flag. |
| `routes/api.py` | Students see only finished sessions' events / reports / CSV / stats. A running session's row hides `total_events`, risk and label from the student. |
| `routes/api_reports.py` | Students refused during the exam. Extra event fields for the report. |
| `routes/stream.py` | `/video_feed` serves a student the raw preview only (no HUD). |
| `app.py` | Evidence route: the student's own images only after the session ended. **The built-in static handler can no longer serve evidence / recordings through dot-path variants** (anonymous bypass, already in phase 1). |
| `modules/reporting/session_report.py` | "Confirmed violations" (HTML / PDF / CSV), direction / duration / risk-added parsing, CSV injection guard. |
| `templates/student/exam.html` | Detection UI removed. Face cadence. Upload instrumentation. Neutral wording. |
| `templates/proctor/dashboard.html` | Long-poll detail video. No blur on the live modal. Grid pause. Current vs confirmed wording. Orientation line. Overall / Current / Cumulative labels. Student-tab-hidden hint. Event-log placeholder fix ("(7)" over 6 events). |
| `tools/live_diag.py` | Runs the same two paths as the server (3 Hz face + 0.8 s YOLO; `--no-fast-face`). Verdicts use eye state and blendshape values. |
| `benchmark/load_test_real_frames.py` | AI uploads at `face_ms`; reports face fps / interval. |
| Tests | See §24. |
| `benchmark/phase2/*` (new) | The measurement tools used for this report: live-video benchmark, simulated student, real-browser head / gaze / evidence test, multi-student browser test, end-to-end replay. See the README there. |
| `FINAL_HEAD_GAZE_LIVE_EVIDENCE_FIX.md` (new) | This report. |

Not changed:
- `modules/detection/phone_detector.py`
- the YAMNet / audio pipeline
- the risk weights and thresholds
- the 4 s rule
- the phone cooldown policy (rows every cooldown while a phone continues, +0)

## 24. Every test added / changed

**New file `tests/test_head_gaze_evidence.py` (16 tests):**
- one episode gives 1 row and 1 clean image; a new episode gives a new one; no image before confirmation
- brief movements create no evidence
- the fast face path does not wait for YOLO
- the student page and API reveal no detection
- the proctor long-poll returns the newest frame and gives preview priority
- the proctor status shows the current detector state
- the report lists confirmed violations with evidence (+ authorisation)
- confirmed-violations parsing (direction / duration / "+0" reasons)
- the densest-cluster calibration fallback
- a second person needs consecutive frames
- browser upload stats reach the proctor, not the student
- the long episode's persistent tier re-uses the image
- the profile direction comes from the detector keypoints
- a failed DB job never leaves a stale session (fails on the phase-1 code, passes now)
- a YOLO-only evaluation does not reset the no-face timer
- browser-event evidence is a raw camera image, never the HUD

**`tests/test_security.py`:** new `test_static_path_variants_cannot_bypass_evidence_protection`; it fails on the phase-1 code and passes now.

**`tests/test_real_runtime_media.py`:**
- New: `test_real_small_face_keeps_a_usable_head_pose` (3 real faces).
- Replaced the down-cast test with `test_real_blink_is_not_looking_down_but_sustained_lowered_eyes_are`.
- `test_real_head_up` disables blendshapes, because that GIF has painted eyes (comment in the test).

**Requirement-driven changes, assertions kept:**

| Test file | Change |
|---|---|
| `test_security.py` | The student is refused report / evidence during the exam and allowed afterwards; the integrity response is `{"status":"ok"}` and sanitising is checked on the worker. |
| `test_video_stream.py`, `test_event_risk_consistency.py::test_status_and_api_agree`, `test_runtime_repairs.py` (3 places) | The student response carries no events / risk; the same facts are now checked on the worker / proctor. |
| `test_lan.py` | `face_ms` in the pace. |
| `test_runtime_repairs.py` (suspended-session test) | Two YOLO frames for the confirmed 2nd person. |

No test was deleted or weakened.

## 25. Full regression counts

Final code, a fresh copy of the tree, Python 3.11 venv, real models (MediaPipe, YOLOv8m, YAMNet) and real test media:

| Check | Result |
|---|---|
| **Full pytest suite** (`tests/`, `test_all.py`, `test_smoke.py`) | **199 passed, 0 failed**, 1 warning, 307 s. Phase 1: 179 passed. The warning is the existing one, a thread exception in `test_isolation_concurrency`'s streaming pump at teardown. |
| New tests (`test_head_gaze_evidence.py`) | 16 passed |
| Real-media tests (`test_real_runtime_media.py`, includes 3 new small-face cases and the new blink / lowered-eyes test) | 12 passed |
| Real YOLO, MediaPipe and YAMNet tests (`test_real_yolo.py`, `test_real_mediapipe.py`, `test_audio_pipeline.py`) | 4 + 3 + 10 passed |
| Risk / event consistency | 19 passed |
| Runtime repairs | 21 passed |
| Security / IDOR / evidence authorisation (includes the new static-bypass test) | 17 passed |
| Video stream | 9 passed |
| JS client test (`node tests/js/test_client.js`) | passed |
| `python -m compileall` | all project modules compile. The one existing exception is `evidence/repro_after.py`, which uses Python 3.12 f-string syntax and fails under 3.11; it is not imported by the app and was not changed. |
| Real browser (Chromium, separate contexts, your recording as camera, final code) | 0 page errors, 0 HTTP 5xx; student page clean for 115 s; Head Right confirmed at 4.3 s held; evidence 403 for the student during the exam, 200 for the proctor and for the student afterwards; all 5 report rows with their images loaded. 2 students: 2 tiles, detail 15.4 fps, 28 ms, no detection wording. 5 students: see §19–21. |
| Live-video benchmark, end-to-end replay of your recording, load test 1 / 5 / 10 / 20 / 30 students | See §19–22. |

## 26. Remaining NOT VERIFIED items

1. **All head / gaze directions on your webcam: NOT VERIFIED ON USER HARDWARE.** Verified on your recording, your screenshots and public real media.
   - Please run `python tools\live_diag.py` and one real exam with `PROCTOR_DIAG=1`, and send the console output, `live_diag_report.json` and the server log.
   - Use two separate windows side by side or two devices, not tabs.
2. **Eyes Down (eyes only) for you:** your neutral eyeLookDown is high (0.43–0.52); looking down gave 0.51–0.58 → mostly not detectable without moving the head. Head-down plus eyes-down is detected.
3. **Eyes Up alone:** blendshape-based; on your frame the up component was measured but the label went to the larger sideways component.
4. **Extreme Head Up** (≥ ~50° tilt back): the landmark model sometimes returns no landmarks, so there is no direction (no keypoint fallback for up / down).
5. **Full-profile fallback:** validated on your profile frame (raw), frontal / 45° frames and the 172 s recording (no false episode). It has not been tested on other people or lighting.
6. **The arm holding a phone can count as a second person** on consecutive YOLO frames (§ Multiple persons).
7. **5+ students in real browsers on one 2-core machine** is CPU-bound (6.6 fps detail). Real separate student devices were not tested here.
8. Chart.js / Tailwind come from CDNs. This sandbox blocks them, so the risk-timeline chart did not render in the screenshots; it is unrelated to these fixes.
9. (Fixed, not open) An intermittent full-run failure of `test_audio_events_propagate_end_to_end` turned out to be a real lost-event-row bug in the DB writer; see § "Intermittent lost event row".

## How to run and test (Windows PowerShell, project folder)

```powershell
.\.venv\Scripts\Activate.ps1          # your existing environment
python run.py                         # as before
# diagnostic run (per-frame [DIAG] lines incl. eyes, head source, browser stats):
$env:PROCTOR_DIAG = "1"; python run.py
# guided webcam check with the SAME pipeline (3 Hz face path + YOLO):
python tools\live_diag.py --show
```

Knobs (defaults in brackets):

| Variable | Default | Effect |
|---|---|---|
| `FACE_FAST_THREADS` | 1 | 0 = previous single path |
| `GAZE_BLINK_CLOSED` | 0.55 | Blink threshold |
| `GAZE_BS_UP_DELTA` | 0.22 | Eyes-up delta over neutral |
| `GAZE_BS_DOWN_DELTA` | 0.30 | Eyes-down delta over neutral |
| `MULTI_PERSON_CONFIRM_FRAMES` | 2 | Consecutive YOLO frames for a 2nd person |
| `WATCHED_PREVIEW_PRIORITY` | 1 | 0 = no 15 fps priority for the watched student |
| `EVIDENCE_MAX_PER_SESSION` | 80 | Evidence cap per session |
