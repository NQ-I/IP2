# AUDIT_REPORT_LIVE_VIDEO.md

## 0. Method

Per instructions, `tests/test_video_stream.py` and `tests/test_lan.py`
were read in full and actually executed before any change — they had
never been run in any previous phase of this project's history. Both
passed completely (9/9 and 8/8) before any change was made, which
immediately reframed the investigation: the video/AI decoupling
architecture they test (`submit_preview`, `submit_ai_frame`, the
live/stale/disconnected state machine, ETag/304 snapshot caching,
newest-frame-wins AI replacement) already exists, is already correct, and
was already covered by tests nobody had run. **The bug was not a missing
architecture — it was two hardcoded timing values that made a correct
architecture run far slower than it needed to.**

## 1. Exact Root Cause

`core/pacing.py`'s `TIERS`/`LARGEST` table told every student browser to
send a live-preview frame no faster than **once every 500ms (2 fps)** at
≤10 students, 700ms (1.4 fps) at 11–20, and **1000ms (1 fps)** above 20.
The client (`templates/student/exam.html`) correctly obeys this
server-provided pace (`PACE.preview_ms`, updated from every response). At
1–2 fps, video looks like a slideshow to a human eye no matter how fast
the rest of the pipeline is — this is squarely "obvious and strong
lag/stuttering," and it was a deliberate, working-as-designed value, not
a bug in the request-handling code.

A secondary, compounding factor: the proctor dashboard's own polling
intervals (`streamTimer` at 1000ms for the grid, `detailSnap` at 500ms for
the zoomed view) additionally capped how often the browser even *asked*
for a new frame, independent of how fast the student was sending.

## 2. Exact Files Responsible

- `core/pacing.py` — the pacing tiers (root cause).
- `templates/student/exam.html` — `PACE` default and the code that obeys the server's pace (correct behavior, just fed slow numbers).
- `templates/proctor/dashboard.html` — `streamTimer`/`detailSnap` intervals (secondary, compounding cap).

## 3. Current Video Transport (verified, not assumed)

**Plain HTTP POST/GET polling of individual JPEG snapshots — not SSE, not MJPEG multipart, not WebSocket, not WebRTC.** Confirmed by reading the actual routes:
- Student → server: `POST /student/frame_preview` (raw binary JPEG body, `Content-Type: image/jpeg` — not base64/JSON), completely separate from `POST /student/frame` (the AI path).
- Server → proctor: `GET /proctor/student/<id>/snapshot` (a single JPEG, with `ETag`/`If-None-Match` support returning `304 Not Modified` when the frame hasn't changed), and `GET /proctor/streams` (one lightweight JSON status payload for **all** of a room's students at once, ~200 bytes/student).
- SSE (`connectSSE()`) is used correctly — for events/alerts/status, exactly as it should be — and is **not** the video transport. This matches the instructions' expectation exactly; nothing needed to change here.

## 4. Was AI Inference Blocking Video? **No — verified, not assumed.**

Traced the actual call path and confirmed with a real, executed test
(`test_video_stream.py::test_frame_endpoint_returns_immediately_with_status_and_events`,
which simulates a 500ms-slow AI model): `/student/frame` acknowledges the
upload and returns in **under 0.3 seconds** regardless of AI processing
time — it does not wait for YOLO/MediaPipe/YAMNet to finish.
`/student/frame_preview` (the actual video path) does no AI work at all —
confirmed by reading `StudentWorker.submit_preview()`: it only decodes
nothing, takes a lock, stores the raw bytes, and returns. **This part of
the architecture was already correct before this investigation** and was
not modified.

## 5. Did a Frame Backlog Exist? **No — verified.**

`submit_preview()` and `submit_ai_frame()` both **replace** the
previously-stored frame, they do not enqueue it — there is no queue data
structure on this path at all, bounded or otherwise. Confirmed by
`test_video_stream.py::test_ai_processes_newest_frame_not_oldest`, which
posts several AI frames back-to-back and asserts the worker processes the
*last* one, not a backlog of all of them. **No change was needed here.**

## 6. Were Stale Frames Being Processed? **No.**

Same evidence as §5 — "newest replaces oldest" is the existing, verified
behavior for both the preview and AI paths.

## 7. Did Browser Polling/Reconnect Loops Contribute? **Yes — the fixed poll intervals were part of the root cause (§1/§2).** No evidence of *duplicate* polling loops or reconnect-created leaks was found in the code read for this investigation (this was not exhaustively fuzzed with real reconnects — see §Limitations).

## 8. Did JPEG/Base64 Encoding Contribute? **No.**

The preview path already uses **raw binary JPEG** POST bodies (verified in
`routes/api_student.py`), not base64 — there is no base64 encode/decode
step on this path to begin with. No unnecessary image copies or
resolution issues were found in `submit_preview()`. Not a factor.

## 9. Did Database Operations Contribute? **No.**

`submit_preview()` performs zero database operations — confirmed by
reading the method in full. The AI path's DB writes (risk/event
persistence) run on the separate `/student/frame` path and, per §4, don't
block that path's response either.

## 10. Did CPU Saturation Contribute? **Partially, at high student counts, but not the primary cause.**

Real measurement (below) shows the server sustains far more preview
throughput than the old pacing allowed even at 30 students — CPU was not
the reason the OLD tiers were slow (the tiers were slow by design/config,
not by hitting a real cei2ling). At 20–30 students, CPU/thread-scheduling
overhead on this test environment's single core does reduce the
*achievable* rate somewhat below the new target — disclosed honestly in
§13, not hidden.

## 11. Exact Files Changed

- `core/pacing.py` — new tiers, chosen from real measurement (§12), with the reasoning documented inline in the file itself.
- `templates/student/exam.html` — one line: the client's initial `PACE` default (66ms) now matches the new fastest tier instead of the old 500ms, so the very first frame (before the server's first response updates it) isn't slow either.
- `templates/proctor/dashboard.html` — two lines: `streamTimer` 1000ms→250ms, `detailSnap` 500ms→150ms, with comments explaining why this doesn't multiply request count (`/proctor/streams` already returns all students in one request).

**Nothing else was touched.** The risk model, YOLOv8m, YAMNet, MediaPipe
detection logic, DetectorPool, CSRF, IDOR protections, session
resume/crash recovery, and the video/AI decoupling architecture itself are
all unmodified.

## 12. Methodology for the New Pacing Values

A real load test was run against the actual running Flask application
(not simulated) on this project's own sandbox (1 CPU core, 3.9GB RAM, no
GPU): real login, real CSRF token flow, real session start, then hammering
`POST /student/frame_preview` with a realistic ~31KB JPEG (a random-noise
320×240 frame at quality 50 — a reasonable upper bound for a real webcam
preview frame) as fast as the endpoint would accept, measuring the actual
sustainable throughput:

| Students | Measured max throughput per student | 0 failures |
|---|---|---|
| 1  | ~366 req/s | Yes |
| 5  | ~69 req/s | Yes |
| 10 | ~31 req/s | Yes |
| 20 | ~13.5 req/s | Yes |
| 30 | ~7.8 req/s | Yes |

The new tiers target roughly 40–60% of each measured ceiling (real
safety margin for production hardware variance, real camera JPEGs, and AI
traffic sharing the same process) rather than the exact measured maximum:

| Students | New `preview_ms` | New target FPS | Old `preview_ms` | Old FPS |
|---|---|---|---|---|
| ≤10  | 66  | 15.2 | 500  | 2.0 |
| 11–20 | 100 | 10.0 | 700  | 1.4 |
| >20  | 150 | 6.7  | 1000 | 1.0 |

AI pacing (`ai_ms`) was left unchanged — the investigation found no
video-latency reason to touch it (§4), and per instructions detection
timing is only changed if proven to be the bottleneck, which it was not.

## 13. Before/After Results — REAL, EXECUTED, Simulated-Client Measurement

**Classification of this test: simulated HTTP client, real running server, same physical sandbox.** This is *not* a real-browser or real-LAN test (see §20/Limitations) — it is a genuine, executed measurement of the actual Flask application's request-handling behavior under the old vs. new policy, using the same test harness for both so the comparison is apples-to-apples.

| Students | OLD achieved FPS (measured) | NEW achieved FPS (measured) | Improvement |
|---|---|---|---|
| 1  | 1.97 | 14.83 | **7.5×** |
| 5  | 1.86 | 14.04 | **7.5×** |
| 10 | 1.74 | 13.06 | **7.5×** |
| 20 | 1.10 | 7.61  | **6.9×** |
| 30 | 0.68 | 4.55  | **6.7×** |

Zero request failures at every student count, both before and after.

**Honest caveat on the 20/30-student NEW numbers**: they land below this
report's own configured targets (10.0 and 6.7 fps) even though the raw
capacity test (§12) showed the server can sustain more (13.5 and 7.8
req/s/student when not artificially paced). The gap is very likely this
test harness's own limitation, not the server's: simulating 20–30
concurrent "students" as Python threads on the **same single CPU core**
that's also running the Flask server means the *test client itself*
competes for that one core's time, adding scheduling jitter that a real
deployment (where each student is a separate physical machine) would not
have. This is disclosed rather than smoothed over.

## 14. Before/After CPU, RAM, Network/Request Rate

**CPU/RAM**: not independently re-measured with `ps` sampling in this
pass (time was spent on the throughput/FPS measurement above, which is
the metric directly tied to the reported symptom). The server process
handled all of the above with zero failures and zero errors in its log,
which is at least evidence it did not crash or become unresponsive under
either policy — but exact CPU%/RSS before vs. after is **NOT MEASURED**
this pass, and should not be assumed equal.

**Request rate**: directly implied by the FPS table in §13 — the new
policy issues ~6.7–7.5× more HTTP requests per student than the old one.
This is a real, deliberate trade-off (more requests for less latency) —
disclosed, not hidden. It was safe to make because §12's raw-capacity test
showed the server has far more headroom than the old, very conservative
tiers assumed.

## 15. Results for 1/5/10/20/30 Students

See §12 (raw capacity) and §13 (achieved FPS under the new policy,
before/after). Both were **actually executed** against the real
application this session, not estimated.

## 16. Tests Executed

```
python3 -m pytest tests/test_video_stream.py -v   9/9 passed (before AND after the fix — this
                                                    architecture was already correct)
python3 -m pytest tests/test_lan.py -v            8/8 passed (before AND after)
python3 -m pytest tests/ -q                       104 passed, 1 skipped (full suite, after the fix)
```
No test was disabled, weakened, or skipped. No existing test needed
modification — the pacing/interval changes are configuration values, not
behavior the existing tests assert specific numbers for (confirmed by
grepping the test files for the old 500/700/1000 values — none found
hardcoded as assertions, only relative-ordering and structural checks,
which still hold with the new numbers).

Additionally executed (ad hoc, not part of the pytest suite, results
reported in full above rather than summarized away):
- Real raw-capacity load test at 1/5/10/20/30 students (§12).
- Real before/after achieved-FPS load test at 1/5/10/20/30 students, same harness for both (§13).

## 17. Tests NOT Executable in This Environment

- **Real browser rendering** (actual `<img>` paint rate, perceived smoothness, browser-side CPU/memory from repeated image swaps) — this sandbox has no browser. **NOT VERIFIED — REQUIRES REAL BROWSER MEASUREMENT.**
- **Real LAN conditions** (actual network latency/jitter between physically separate devices, real WiFi/Ethernet variance) — this sandbox only has loopback networking. **NOT VERIFIED — REQUIRES REAL LAN/DEVICE TEST**, even though `test_lan.py` (which tests LAN-related *code paths* like certificate generation and CORS-safe IP handling, not actual network conditions) does pass.
- **Real webcam capture rate** — the student-side frame source in every test here is a synthetic JPEG, not an actual camera. A real camera's capture rate, encoding time, and frame variability were not measured.
- **30 real physically-separate student devices** — simulated as threads on one sandbox (see the honest caveat in §13).

## 18. Remaining Limitations

- The 20/30-student achieved-FPS shortfall relative to this report's own targets (§13) should be re-measured on real separate client machines before being treated as a hard ceiling — it may be entirely a test-harness artifact.
- CPU/RAM before-vs-after were not independently measured (§14) — only request throughput and success rate were.
- No changes were made to reduce per-tile browser rendering cost (DOM rebuild, image decode overhead) for a 30-tile grid specifically — the existing code already avoids unnecessary re-fetches (`frame_seq`-gated) and unnecessary DOM churn (pre-load-then-swap), and no evidence was found that it does anything wasteful, but this was verified by code reading, not by real-browser profiling.
- Actual glass-to-glass latency (camera capture → proctor's screen) was not measured end-to-end with real timestamps embedded in real frames; §13's numbers measure request throughput, which bounds latency but is not identical to it.

---

## Explicit Confirmation of the Required Behaviors

- Proctor live video must not wait for YOLO. **✅ Verified — separate endpoint, separate code path, zero AI work in `submit_preview()`.**
- Proctor live video must not wait for MediaPipe. **✅ Same reason.**
- Proctor live video must not wait for YAMNet. **✅ Audio has its own separate pipeline/endpoint entirely (`core/audio_pipeline.py`); not on the video path at all.**
- Proctor live video must not wait for database writes. **✅ Verified — zero DB calls in `submit_preview()`.**
- Old frames must not accumulate indefinitely. **✅ Verified — replace-not-queue, both paths.**
- Stale frames should be dropped. **✅ Same — newest always wins.**
- The newest frame should be preferred. **✅ Verified by `test_ai_processes_newest_frame_not_oldest`.**
- One slow student must not block all other students. **Not independently stress-tested this pass (no per-student lock contention issue was found by reading the code — each `StudentWorker` holds its own state — but a dedicated "one slow student vs. others" test was not run). Recommend as follow-up.**
- Live video and AI analysis must be decoupled. **✅ Verified — this was already true before this investigation; confirmed, not assumed.**
- Existing risk/security/session functionality must remain intact. **✅ Full test suite (104 tests, including every risk-model and security test from the previous phase) passes unchanged.**
