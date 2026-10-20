# Phase 3 — smooth live video and warnings for the student

This phase made only the two requested changes and fixed problems found in the screenshots and log you sent. Nothing else was changed:

- detection
- risk model
- phone / YAMNet
- reports
- authorization

## 1. Why the proctor saw "moving pictures"

Your proctor screenshot shows `stream: live · 1.6 fps · capture→display 1033 ms · student exam tab HIDDEN`. In your test, the student's exam window (Chrome) was behind the proctor's window (Edge) on the same computer.

The exam page captured and sent the camera with **page timers** and the page's own `<canvas>`. The browser runs a covered or hidden page's timers at most once per second and delays its canvas encoding. The result was about 1 frame per second, arriving about 1 s late.

**Reproduction.** I reproduced this in real Chromium (headful, with normal background throttling) by putting the student page behind another tab:

| Student page | Proctor sees |
|---|---|
| visible | 15.6 fps |
| hidden | **1.0 fps**, gaps 1016 ms, capture → arrival 1017 ms ("encode 907 ms") |

**Fix.** The camera upload pipeline now runs in a **dedicated worker** (`static/js/capture_worker.js`):

- **Frame source.** Frames come straight from the camera track: `MediaStreamTrackProcessor` → `ReadableStream`, transferred to the worker. No page timers and no page canvas are involved.
- **Encoding and upload.** The worker scales and JPEG-encodes on an `OffscreenCanvas` and uploads from the worker.
- **No backlog.** There is one request in flight per channel. Frames that arrive meanwhile are dropped, so the newest frame always wins and nothing queues.
- **Fallback.** Browsers without `MediaStreamTrackProcessor` (Firefox, old Safari) use the previous page loop. The page also switches automatically to that loop if the worker has no accepted upload within 6 s.

## 2. Better quality and smoothness for the selected student

- **Selected student.** While a proctor has a student's detail view open, that student's browser sends **640 px wide, JPEG q0.75, up to 30 fps**. Before, it sent 320×240, q0.5, 15 fps.
- **Other students.** Everyone else keeps the small grid preview, 320×240 at the class-size rate.
- **Settings.**

| Variable | Default |
|---|---|
| `WATCHED_PREVIEW_MS` | 33 |
| `WATCHED_PREVIEW_WIDTH` | 640 |
| `WATCHED_PREVIEW_QUALITY` | 0.75 |

- **Grid tiles.** They refresh faster in small classes:

| Class size | Tile rate |
|---|---|
| ≤ 4 students | 10 frames/s |
| ≤ 10 students | ~6.7 frames/s |
| larger | 4 frames/s |

**Measured.** All on one 2-core machine running the server, the proctor browser and the student browser at the same time, which is CPU-bound:

| | Before | After |
|---|---|---|
| Student page **hidden**: selected student fps | 1.0 | **24** (23.9–24.7) |
| Hidden: capture → arrival p50 / p95 | 1017 / 1025 ms | **25–40 / 49–77 ms** |
| Student page visible: selected student fps | 15.6 (320×240) | **21–23 (640×480)** |
| Grid tile fps (1 student) | 4.0 | **10.0** |

On a computer with more cores the selected student should approach the 30 fps target. This is **NOT VERIFIED ON USER HARDWARE**.

**Tried and reverted.** Encoding the next frame while the previous one uploads gave about +1–2 fps but +16–29 ms latency. It was reverted.

## 3. Warnings for the student

The student now gets a **warning when a violation is confirmed**, not only the proctor:

- a red "Warning" toast at the top of the page, using the page's existing warning toast
- a red line in "Session notices", for example:
  - "Looking / facing away: Head turned right"
  - "Phone detected"
  - "Multiple people in frame"
  - "Face not visible"
  - "Speech detected"
  - "Switched away from exam tab"
  - "Copy attempted"

How it works:

- **Timing.** Warnings follow the same confirmation rules the proctor sees, for example the 4 s head / gaze hold. Brief movements still give nothing.
- **One warning per event.** A continuing episode gives one warning. A page reload does not replay old warnings: the start response carries `event_seq`.
- **Delivery.** Warnings travel with the answer to each AI frame (`warnings: [{seq, type, message, severity, time}]`).

Still **not** shown to the student, unchanged:

- risk score or percentage, cumulative risk
- confidence
- the detector's live state (current gaze / head)
- evidence images during the exam

**Real browser check** (normal throttling), student page only: a copy attempt and a right-click each produced a toast and a notice ("Copy attempted", "Right-click attempted"). The proctor received the same 2 events. No risk text or percentage appeared on the page. The result was identical with the worker and with the page-timer fallback.

## 4. Your log and screenshots

The log excerpt covers 3 s (21:25:30–33), during calibration while the student was turned about 45°. Everything in it behaves as designed:

- browser `send=15.0fps`
- `face=3.00fps`
- `ai=1.25fps`
- `tab=visible`
- head pose not yet valid because calibration had not finished

No error is visible in it.

The high risk in your screenshot comes from "Window lost focus" and "Switched away from exam tab". Every switch from the student window to the proctor window **is** such a violation. When you test on one computer, keep both windows visible side by side so that you do not switch away from the exam.

## Files changed in phase 3 (vs phase 2)

| File | Change |
|---|---|
| `static/js/capture_worker.js` (new) | The camera upload worker |
| `templates/student/exam.html` | Starts / stops the worker (fallback: the old loop); shows warnings (toast + notices); the fallback loop uses the server's preview size / quality |
| `templates/proctor/dashboard.html` | Adaptive grid tile rate |
| `core/pacing.py` | `preview_w` / `preview_h` / `preview_q` in the pace; 30 fps, 640 px, q0.75 for the watched student |
| `routes/api_student.py` | `warnings` in the AI-frame answer; `event_seq` in the session-start answer |
| `tests/test_head_gaze_evidence.py`, `tests/test_lan.py` | Requirement change: the student now gets warnings, and the pace has preview size / quality |
| `benchmark/phase2/hidden_window_bench.py`, `benchmark/phase2/browser_student_warnings.py` (new) | Measurement / browser tests used above |

## Regression

| Check | Result |
|---|---|
| Full suite | **199 passed, 0 failed** |
| JS client test | passed |
| Real browser runs | 0 page errors (only `/favicon.ico` 404, as before) |
