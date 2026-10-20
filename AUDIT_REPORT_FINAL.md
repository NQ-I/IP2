# AUDIT_REPORT_FINAL — AI-Based Online Exam Proctoring System

Scope: full end-to-end audit, debugging and improvement pass over the whole project ZIP.
Status vocabulary used everywhere: **VERIFIED** · **PARTIALLY VERIFIED** · **NOT VERIFIED** · **KNOWN LIMITATION** · **NOT TESTED**.

Audit environment (all measurements below come from it): Linux sandbox, **1 vCPU, 4 GB RAM**, Python 3.12.3, TensorFlow 2.21,
MediaPipe 0.10.33, PyTorch 2.14 (CPU execution, no GPU), Ultralytics 8.4.157, scikit-learn 1.7.2, numpy 2.4.4 (the project pins `numpy<2`;
a pip dry-run resolves `requirements.txt` consistently with numpy 1.26.4, but the pinned set was not executed here).
**Windows was not available**, and **no browser** was available: browser behaviour and real multi-device operation are NOT VERIFIED.
The earlier drafts of this report said YOLO could not run in the sandbox; that is superseded by the "Final verification pass" below
(the CUDA wheels were eventually installed after freeing disk space).

---------------------------------------------------------------------------------------------------

## 0. Final verification pass (latest state — supersedes any older statement in this file)

| Item | STATUS | EVIDENCE |
|---|---|---|
| Full test suite, run 1 | **VERIFIED** | `test_all.py` 25 passed + `test_smoke.py` & `tests/` 113 passed = **138 passed, 0 failed** |
| Full test suite, run 2 | **VERIFIED** | 25 passed + 113 passed = **138 passed, 0 failed** |
| Node tests (`tests/js/test_client.js`) | **VERIFIED** | all assertions passed |
| Byte-compile, pyflakes (undefined names), import of all 48 modules one by one (circular imports) | **VERIFIED** | clean |
| YOLOv8m with Ultralytics (real weights, real inference) | **VERIFIED on Linux/CPU** | `tests/test_real_yolo.py` (4 passed): `models/yolov8m.pt` loads, real photos → 4 persons + bus (`bus.jpg`), 2 persons (`zidane.jpg`); `PhoneDetector` backend `YOLOv8m+Verifier+Tracker+AntiBypass+Ensemble`, phone id 67 / person id 0; the application pipeline turned the real photo into a `multiple_persons` event → risk reason → DB row |
| YOLO on **Windows** | **NOT VERIFIED** | no Windows machine |
| Phone detected in a **real phone photo** | **NOT VERIFIED** | no such image ships with any package; needs your dataset (`datasets/phone_proctoring`, `benchmark/phone_detection_benchmark.py`) |
| YOLO speed | measured, 1 vCPU | 0.42–0.58 s/frame raw, 0.6–0.8 s/frame through `PhoneDetector` (two scales + verifier) |
| Person counting design | KNOWN LIMITATION | a person must cover ≥ 10 % of the frame to count (`MIN_PERSON_AREA_FRAC`); `bus.jpg` (4 small persons) therefore counts 1. Threshold not changed |
| MediaPipe face analysis | **VERIFIED** | `tests/test_real_mediapipe.py` (3 passed): real portrait → 1 face, yaw ≈ 0°; blank image → 0 faces; real pipeline run without errors. Head-pose/gaze validity flags stay False during the analyser's calibration phase by design |
| YAMNet | **VERIFIED (loading/inference/plumbing)** | live server reports backend `YAMNet`, `load_error: null`; accuracy on real speech/whisper/typing NOT VERIFIED — REAL DATASET REQUIRED |
| Random Forest | **VERIFIED (loads, predicts)** | shared once per process; scikit-learn pinned to 1.7.2 (the pickle's version) → 0 version warnings. Trained on synthetic data; does not drive the displayed risk |
| Server crash + restart (real `run.py --https --port 5000`, `kill -9`) | **VERIFIED** | old cookies still valid; proctor sees the student as a `db_only` "reconnecting" card with the same session id; the student's next frame resumes the session; both events (seq 1 and 2) present, no duplicates; DB rows match |
| `tools/lan_smoke_test.py` over real HTTPS (real YOLO+MediaPipe+YAMNet on the server) | **VERIFIED** | 2 students 18/18 checks; 30 students 242/242 (earlier runs: 5 → 42, 10 → 82, 20 → 162, all passed); 0 tracebacks in the server logs |
| Server binding / HTTPS | **PASS** | `0.0.0.0:5000`, certificate valid for the LAN IP, plain HTTP on the HTTPS port refused, cookies `Secure; HttpOnly; SameSite=Lax`, POST without CSRF → 400 |
| Real browsers, camera/microphone permissions, certificate-warning flow, real multi-device operation | **NOT VERIFIED** | no browser/second device; only simulated clients over real HTTPS |
| Windows install of `requirements.txt` | **NOT VERIFIED** | pip resolver dry-run (Linux, Python 3.12) is consistent |
| PostgreSQL | **NOT VERIFIED** | no server; `postgres://` URLs are normalised; SQLite is what was tested |
| Original database | **VERIFIED** | `instance/proctor.db` in the package is byte-identical to the one in the ZIP you uploaded (sha256 `874df50d…`). The legacy tests used to rewrite it (3 `exam_sessions` rows lost their `student_id`); a root `conftest.py` now points every test at a throw-away database, and the hash was unchanged after both final full-suite runs. The app upgrades the file on first start (WAL mode + new columns) |

Fixed in the final passes (in addition to §2–§19): evidence paths stored with Windows backslashes (all 21 rows of the shipped DB were affected → evidence 404; now
normalised to `/` at startup and stored that way); `/student/session/start` accepted nonexistent rooms (ghost sessions invisible to every proctor);
students missing from the dashboard when their live worker was gone (database fallback: `db_only` cards, `resume_session`, hydration of events and risk);
orphan/zombie open sessions and duplicate open sessions per student; watchdog thread killed by a single exception; ending a room did not finalise live sessions;
the Random Forest pickle was loaded per student and was built with a scikit-learn version the requirements did not pin; `requests`/`Pillow` missing from
requirements; hard-coded `C:\Projects` path in `start.bat`; second HTTPS-less entry point (`app.py`); Linux-only `mv` hint; SQLite now uses WAL + busy timeout;
console output forced to UTF-8 for Windows; all Arabic text translated to English (`LAN_GUIDE.md` replaces the Arabic guide); historical documents moved to `docs/history/`.
One existing test was adapted: the legacy deadlock test in `test_all.py` used a flat 60 s budget written for the MediaPipe fallback; with real YOLO 120 serialized
frames legitimately need ~90 s, so the budget now scales with the measured per-frame time (a genuine hang still fails).

**Privacy:** `static/recordings/` (one exam video) and `static/violations/` (several hundred evidence frames) contain real captured data of people from earlier demo
sessions. They were left untouched (not modified, not deleted). Remove them and the matching database rows before sharing the project.

Sandbox-only note: `import triton` segfaulted in the sandbox, so the (CPU-irrelevant) `triton` package was uninstalled there; it is not a project dependency.

---------------------------------------------------------------------------------------------------

## 1. Executive summary

| Area | Result |
|---|---|
| "Risk 80–97 % but Events 0 / no alerts" | Root cause reproduced on the original code and fixed. Every risk point is now attributed to a recorded event; risk > 0 ⇒ ≥ 1 event (invariant tested on 300-step random sequences). **VERIFIED** (with test-double detectors; see limits) |
| "Stream: Error" while frames flow | Root cause found by code reading (latched error label). Replaced by a freshness-based state machine + server-side stream status. State machine **VERIFIED** (Node), the page itself **NOT TESTED in a browser** |
| Live video vs AI | Preview path never touches AI/DB; newest-frame-wins slots; bounded scheduler. **VERIFIED** (tests + load test) |
| YAMNet | Real local SavedModel loads and runs; correct 16 kHz contiguous input path; official class map; honest labelling. **VERIFIED** for loading/inference/plumbing; accuracy on real speech **NOT VERIFIED — REAL DATASET REQUIRED** |
| Phone detection | `yolov8m.pt` intact; class ids resolved by name; real YOLO inference **VERIFIED on Linux/CPU** (see §0); phone accuracy on real phone photos NOT VERIFIED |
| 30 students | Measured on 1 vCPU (see §10): 30/30 sessions, 0 errors, 0 event loss, 0 cross-student contamination, preview never stale. AI analysis rate per student falls to 0.2 fps at 30 students on this hardware. **PARTIALLY VERIFIED** (single core, MediaPipe fallback, simulated browsers) |
| Security | 12 issues fixed and regression-tested (§11) |
| Datasets | Nothing downloaded/generated. Structure, READMEs, validators, training/eval/benchmark scripts, auto-discovery ready. All benchmarks print `NO REAL DATA AVAILABLE — BENCHMARK NOT RUN` and exit 0 |
| Tests | 112 tests (legacy 41 + new 71); final full-suite results are recorded in §13 — see the honest note on an earlier flaky run |

---------------------------------------------------------------------------------------------------

## 2. Bugs discovered

Reproduction of the central bug on the ORIGINAL code (test-double detectors; real `StudentWorker` logic;
`evidence/repro_before.py`, output in `evidence/before_repro.txt`):

| Scenario | ORIGINAL | FIXED (`evidence/after_repro.txt`) |
|---|---|---|
| 3 browser-integrity violations | risk **1.00 High**, worker events **0**, `top_event` None, no alerts | risk 0.87 High, **3** events, each listed in risk reasons |
| Phone flickering on/off for 30 frames | risk **1.00 High**, 2 events | risk 0.59, 2 events, capped per event type |
| One suspicious audio report | 3 events from the *same* report; `audio_event` stayed "speech" forever | 1 event after 2 confirming windows; result expires after 6 s (`no_audio`) |
| Sustained no-face | event severity **Low** (invisible in the student's Medium/High-only counter) | severity Medium |
| Sustained phone 18 s | risk 0.43 | risk 0.60 (persistence weights now actually accrue — a **behaviour change**) |

| # | Bug | Where |
|---|---|---|
| B1 | Integrity violations (fullscreen/tab/devtools/clipboard) raised risk but produced no worker event, no `top_event`, no student alert; the SSE message used a *different schema* (nested `data`) than worker events and would break the dashboard modal (`event_type` undefined) | `routes/api_student.py:/integrity`, `student_worker.py` |
| B2 | Risk gained a full +0.42 on every rising edge of a flickering detector while events were throttled → risk saturates from one physical object | `_accumulate_risk` |
| B3 | Audio result never expired; risk/event logic re-read it every frame | `_check_events` |
| B4 | Student "Events"/"Session notices" were built only from the alerts inside the response of the single request that processed a frame (and only Medium/High counted) → any lost/slow response hid events | `exam.html`, `submit_frame` |
| B5 | "Stream: Error" is set on *any single* failed frame request and never reset on success. Preview upload was fire-and-forget with no timeout / in-flight guard. CSRF token fetch failure was cached forever; the token expires after 1 h | `exam.html` |
| B6 | Session watchdog only counted AI-pipeline completions as activity → a healthy preview/audio stream could still get the session reaped after 120 s | `student_worker.py`, `session_manager.py` |
| B7 | YAMNet could never work: (a) code imported `tensorflow_hub` (not needed, not in requirements, TF commented out); (b) the SavedModel artifact has **no class map**, so every label was "unknown"; (c) the browser sent five 85 ms reads taken 60 ms apart (~0.4 s of overlapping, discontinuous audio) while YAMNet needs ≥ 0.975 s continuous; (d) the mapped classes "male/female speech" do not exist in YAMNet's 521 classes | `audio_analyzer.py`, `exam.html` |
| B8 | Proctor dashboard event counters/feed came only from SSE (0 on page load or after reconnect); SSE broadcast **every room's events to every proctor**; a full queue silently *removed* the subscriber; the client re-opened the connection manually on top of EventSource's own retry | `event_bus.py`, `api_proctor.py`, `dashboard.html` |
| B9 | Security — see §11 | several |
| B10 | `PHONE_CLASS_ID=67 / PERSON_CLASS_ID=0` hard-coded: a model fine-tuned with the shipped `data.yaml` (`0: phone`) would have been read as "class 0 = person" and never fire | `phone_detector.py` |
| B11 | Shipped "benchmark" artifacts were computed from computer-drawn scenes / generator-made features (precision = recall = 1.0; RF 0.91) — presented next to real-evaluation scripts | `benchmark/` |
| B12 | `requirements.txt` had TensorFlow commented out and required `tensorflow-hub`; `data.yaml` used a relative `path:` that Ultralytics resolves against its own `DATASETS_DIR`; all training scripts demanded `--data` | requirements, training |
| B13 | Dead code / unused variables in the risk engine (`head_sustained`, `attn_sustained`, unreachable body after `return`); two different level thresholds (0.31/0.61 in the worker vs 0.35/0.65 in the classifier) | `student_worker.py` |
| B14 | The dashboard did a full `innerHTML` rebuild of every card (incl. the `<img>`) each 2.5 s poll → reloading every tile image | `dashboard.html` |
| B15 | *Found by my own tests during this pass:* scheduler was not attached to workers (silent patch miss → AI never ran; my first assertion was too weak to notice); proctor ownership cache was process-global and leaked verdicts between apps/DBs (flaky test) | `session_manager.py`, `api_proctor.py` |

---------------------------------------------------------------------------------------------------

## 3. Bugs fixed (summary; details in the sections below)

B1–B8, B10–B15 fixed. B9 fixed as listed in §11. Each has a regression test (§13) except where marked NOT TESTED.

---------------------------------------------------------------------------------------------------

## 4. Architecture changes

Three independent paths that never wait for each other:

```
REAL-TIME PATH  browser --raw JPEG--> /student/frame_preview --> worker "latest preview" slot --> /proctor/.../snapshot
                (no decode, no AI, no DB)                                                          (ETag, freshness headers)
HEAVY AI PATH   browser --raw JPEG--> /student/frame --> worker "pending AI frame" slot (newest wins, older REPLACED+counted)
                                          |                       ^
                                          +-- returns at once     +-- AIScheduler threads (= detector-pool size), round-robin,
                                              with latest status      one pending frame per student, ready-queue ≤ #students
PERSISTENCE     events / risk snapshots / evidence files --> ONE bounded queue + ONE writer thread (retry on transient errors,
                inline fallback if the queue is full, counters exposed)
AUDIO           browser 16 kHz Int16 PCM (~1 s, contiguous) --> /student/audio (202) --> 3 s ring buffer per student
                --> ONE inference thread --> shared YAMNet --> worker.ingest_audio() --> same event/risk funnel
```

New/changed modules: `core/risk.py` (weights, caps, cooldowns, labels, thresholds — one source of truth),
`core/event_log.py` (normalized events, coalescing), `core/telemetry.py`, `core/ai_scheduler.py`, `core/audio_pipeline.py`,
`core/event_bus.py` (ids, replay ring, overflow → `resync`), `core/student_worker.py` (rewritten around the above),
`static/js/proctor_client.js` (DOM-free helpers, unit-tested).

Kept as-is on purpose: FaceAnalyzer/PhoneDetector internals, verifier/tracker/anti-bypass/ensemble logic, DetectorPool
(state externalisation via `get_state/set_state`, try/finally release), reporting, RBAC model.

---------------------------------------------------------------------------------------------------

## 5. Detection → event → risk → dashboard pipeline

Each signal has ONE predicate used for both the event and the risk (previously two slightly different predicates):

| Signal | Event type / severity | Risk (unchanged weights) |
|---|---|---|
| CONFIRMED phone (≥ 0.55) | `phone_detected` High, cooldown 12 s | +0.42 episode, +0.018/s while continuous, cap 0.80 |
| MONITOR-tier phone (≥ 0.35, only when no confirmed phone) | `phone_suspected` Medium, 8 s | +0.16, +0.004/s, cap 0.30 |
| > 1 person | `multiple_persons` High, 15 s | +0.42, +0.025/s, cap 0.80 |
| no face ≥ 5 s | `no_face` Medium, 8 s | +0.12, +0.006/s, cap 0.40 |
| gaze/head deviation ≥ 4 s, conf ≥ 0.5 | `orientation_deviation` Medium, 8 s | +0.12, +0.006/s, cap 0.30 |
| speech / whispering / shout (audio) | `audio_*` Medium, 10 s, 2 windows in 6 s to confirm | +0.10 / +0.08 / +0.12 |
| browser integrity (fullscreen, tab, blur, copy/cut/paste, context menu, devtools) | `integrity_*` (Low–High), 3 s | 0.06 – 0.35 per kind; informational kinds add none |

* Event fields: `seq, event_id, session_id, student_id, student_name, room_id, event_type, severity, confidence, description,
  source (detector/backend), timestamp (UTC ISO), repeat_count, evidence_path, contribution`.
* Repeats inside the cooldown are **coalesced** (`repeat_count`, max confidence) instead of dropped; after the cooldown a new event with
  its own evidence frame is opened, so a phone in view for a minute yields ~1 event / 12 s, not one per frame and not one in total.
* Flicker shorter than 2.5 s counts as the same episode (no repeated +0.42).
* Risk = Σ per-type terms, each decaying with a 45 s half-life; `risk_reasons` lists label, points, share, event count, repeat count,
  last seen. Risk is computed lazily at read time, so an integrity event changes it immediately even if the AI is slow.
* Sinks: worker log → student API (`/student/events`, `/student/frame` response) → DB (`behavior_events` + new `source`,
  `repeat_count`, `seq` columns; atomic `total_events` increment) → SSE (`event`, `event_update`) → proctor dashboard →
  session report / CSV (`Repeats`, `Source`, `Evidence` columns).
* Face touching (`head_position_anomaly`) remains an analytics signal **by design** (no event, no risk) — KNOWN LIMITATION.

| Feature | STATUS | EVIDENCE | TEST | LIMITATION |
|---|---|---|---|---|
| Event/risk consistency | VERIFIED | `evidence/after_repro.txt` | `tests/test_event_risk_consistency.py` (8) | detectors are test doubles; real-detector accuracy is not measured |
| Event reaches student API, proctor API, DB, SSE, evidence file, report | VERIFIED | tests read each sink | `test_status_and_api_agree`, `test_audio_events_propagate_end_to_end`, `test_evidence_files_are_access_controlled` | — |
| Person detection → event with real YOLO | VERIFIED (Linux/CPU) | `tests/test_real_yolo.py` | 4 passed | phone-in-real-photo NOT VERIFIED |
| Risk thresholds | PARTIALLY VERIFIED | one table in `core/risk.py` (0.31 / 0.61) | `test_random_signal_sequences_keep_invariant` | `modules/ml/classifier.py` still uses 0.35/0.65 for its own label; the RF is trained on synthetic data and is not used for the displayed risk |

---------------------------------------------------------------------------------------------------

## 6. Audio / YAMNet status

* Model: `models/yamnet/saved_model.pb` (+ `variables/`), sha256(saved_model.pb) `672af6e1…`; loads with `tf.saved_model.load`
  (no `tensorflow_hub`); callable returns `(scores[N,521], embeddings, spectrogram)`.
* Class map: the artifact shipped without one. I added the **official 521-row `yamnet_class_map.csv`** from the
  `tensorflow/models` repository (sha256 `cdf24d19…6df2`) at `models/yamnet/assets/` and `models/`. It is a label file, not a dataset —
  please verify or replace it if your rules require. Class groups are resolved from it **by display name** at load time
  (`status()["missing_class_names"] == []` is asserted); no label is invented. Note "Male speech"/"Female speech" are not YAMNet classes;
  "Rustle" (481) *is*, but nothing is mapped to it and no "paper"/"chair" claim is made.
* Input contract: mono float32, resampled to 16 kHz; < 0.975 s → `insufficient_audio` (never classified from zero padding);
  digital silence (RMS < 0.0015) skips inference and says so (`decision: rms_gate_silence`, `inference_ran: false`).
* Result: `event ∈ {speech, whispering, shout, typing, silence, background_noise, other, unknown}`, `confidence`,
  `is_suspicious` (speech/whispering/shout only), `backend`, `inference_ran`, `group_scores`, `top_classes`, `infer_ms`.
* Fallback: if TensorFlow/model/class map fails, backend = `"energy-variance fallback"`, `status()["load_error"]` holds the exact reason
  (tested: missing model dir, missing class map). It is never labelled YAMNet. `GET /admin/runtime` (admin only) shows it live.
* Browser: `startAudioCapture()` (ScriptProcessor → streaming box-filter resampler → 16 kHz Int16 PCM, ~1 s per POST, in-flight guard,
  ≤ 3 s buffer). Resampler tested in Node at 48 kHz and 44.1 kHz (frequency preserved; chunk boundaries seamless).

Measured in the sandbox (1 vCPU): YAMNet load ≈ 2.4 s after TF import (TF import ≈ 25–30 s cold); **12–25 ms per 2 s window**;
1037 windows classified during the 30-student run with 0 errors.

| Test input (real inference) | Result |
|---|---|
| silence (zeros) | `silence`, not suspicious, inference skipped by RMS gate |
| 0.4 s tone | `insufficient_audio` |
| 1 kHz tone, white noise | real AudioSet labels (e.g. "Beep, bleep", water/noise classes), not suspicious |
| **speech, whispering, typing, keyboard, real background noise** | **NOT VERIFIED — REAL DATASET REQUIRED** (no real audio available; not fabricated). Speech-event *propagation* is tested with a labelled test double |

Thresholds (`speech 0.45`, `whispering 0.35`, `shout 0.45`) are the previous project defaults and are **uncalibrated**.

| Feature | STATUS | EVIDENCE | TEST | LIMITATION |
|---|---|---|---|---|
| YAMNet load + inference from local model | VERIFIED | runtime + `status()` | `test_yamnet_local_model_is_actually_loaded_and_used` | needs `pip install tensorflow` |
| Honest fallback labelling | VERIFIED | tests for both failure modes | `test_missing_model_reports_exact_reason…`, `…class_map…` | — |
| Audio → event → risk → DB → SSE → dashboard | VERIFIED (double classifier) | end-to-end test | `test_audio_events_propagate_end_to_end` | real speech accuracy NOT VERIFIED |
| Browser capture | PARTIALLY VERIFIED | Node DSP tests, syntax check | `tests/js/test_client.js` | no browser/microphone test |
| Accuracy (speech/whisper/typing/noise) | NOT VERIFIED — REAL DATASET REQUIRED | — | `training/audio_benchmark_real.py` | — |

---------------------------------------------------------------------------------------------------

## 7. Phone detection status

* `models/yolov8m.pt`: **unchanged**; 52,136,884 bytes, sha256 `5d4a90cd…e4fe5`; valid PyTorch archive whose embedded class names
  contain `cell phone` at COCO index 67 (read statically). `tests/test_misc_infra.py::test_yolov8m_weights_intact`.
* Ultralytics import, real weight loading, COCO mapping at runtime and real inference: **VERIFIED on Linux/CPU** (§0, `tests/test_real_yolo.py`). The MediaPipe-EfficientDet fallback is used only when `ultralytics` is missing.
* Fixed: class ids are now resolved from `model.names` by name (`resolve_class_ids`) so both the COCO baseline and a single-class
  fine-tune work; a model without a phone class fails loudly at load. A single-class model has no `person` class →
  multi-person detection is unavailable with it (KNOWN LIMITATION, documented in the dataset README).
* No claim of improved accuracy is made. Fine-tuning pipeline is ready but **not run**: **NOT VERIFIED — REAL DATASET REQUIRED**.

---------------------------------------------------------------------------------------------------

## 8. Event / alert pipeline (proctor side)

* Dashboard loads the last 100 persisted events on page load/room switch (`/proctor/events/recent`) — the feed and counters no
  longer depend on having been connected when the event happened; de-duplication key `session_id:seq`.
* SSE: `id:` per message, native `Last-Event-ID` replay from a 500-message ring, `resync` on overflow/gap, heartbeat, and
  **per-proctor room scoping**. `event_update` refreshes repeat counts.
* Cards show stream badge, risk %, "N events", top-3 risk reasons, evidence links; modal shows reasons, stream state/age,
  and switches between the raw live frame and the AI-annotated frame.
* Every untrusted string is HTML-escaped; inline-JS string interpolation replaced by `data-*` attributes.

| Feature | STATUS | EVIDENCE | TEST | LIMITATION |
|---|---|---|---|---|
| SSE scoping / replay / overflow | VERIFIED | live SSE read in test; bus unit test | `test_sse_scoped_to_owned_rooms`, `test_event_bus_replay_and_resync` | the bus is process-local (§18) |
| Dashboard rendering & JS behaviour | PARTIALLY VERIFIED | pages render (Jinja), all inline JS passes `node --check` | `test_pages_render_without_template_errors` | **NOT TESTED in a browser** |

---------------------------------------------------------------------------------------------------

## 9. Live video pipeline

* Student page: preview every 500 ms (raw JPEG blob, 4 s timeout, one request in flight, exponential back-off, newest frame each
  time); AI frame every ≥ 800 ms (6 s timeout). Health per channel = freshness of the last **accepted** request.
* "Stream" label states: **Live** (< 4 s since last accepted preview) · **Reconnecting…** · **Server error** (HTTP ≥ 500 and stale) ·
  **Disconnected** (> 15 s) · **Session lost** (server `no_session` → the page re-joins once) · **Starting…**. A single failed request after a
  success can no longer show an error (regression assertion in `tests/js/test_client.js`). "Analysis" and "Audio" have their own indicators.
* Server: `stream` block in every status and `GET /proctor/streams` (≈ 200 B/student, polled 1 Hz): `state ∈ {live (<3 s), stale (<10 s),
  disconnected, waiting, no_signal}`, `frame_age_ms`, `frame_seq`, source, preview fps, AI fps/state/latency/queue delay/replaced/errors.
* Snapshot endpoint: `X-Frame-Seq`, `X-Frame-Age-Ms`, `X-Frame-Source`, `X-Stream-State`, ETag → 304 when unchanged. The modal polls at 2 Hz
  conditionally; grid tiles at 1 Hz with pre-loaded images (no flicker, persistent `<img>`).
* Ownership checks on the snapshot route are cached 10 s **per app** (previously 3 DB queries per image request).

| Feature | STATUS | EVIDENCE | TEST | LIMITATION |
|---|---|---|---|---|
| Preview independent of AI | VERIFIED | preview submit max < 50 ms while AI takes 300 ms/frame | `test_preview_never_waits_for_slow_ai` | — |
| Newest-frame-wins, bounded | VERIFIED | AI processed the newest of 8 queued frames; received = processed + replaced + ≤ 2 | `test_ai_processes_newest_frame_not_oldest` | — |
| Stream state machine / stale / recovery | VERIFIED | server states and JS state machine | `test_stream_state_machine_live_stale_disconnected`, `tests/js/test_client.js` | UI wiring NOT TESTED in a browser |
| Real browser latency | NOT TESTED | — | — | numbers in §10 are in-process |
| Smooth "video" | KNOWN LIMITATION | tiles ≈ 1 fps, modal ≈ 2 fps (limited by the 2 fps upload) | — | true smooth video needs MJPEG/WebRTC (not implemented, not faked) |

---------------------------------------------------------------------------------------------------

## 10. 30-student scalability — MEASURED

> These in-process numbers were measured with the MediaPipe fallback phone backend. With the real YOLOv8m backend each AI frame costs 0.6–0.8 s on one core (§0), so the AI rate per student at 30 students is lower still; the live-view path is unaffected because it never runs AI. The real-HTTPS smoke test with YOLOv8m active passed for 30 simulated students (§0).

Harness: `benchmark/load_test_inprocess.py` (reproducible: `python benchmark/load_test_inprocess.py --levels 1 5 10 20 30 --duration 40`;
raw results `reports/load_test_results.json`). Real routes, SessionManager, scheduler, **real MediaPipe face + MediaPipe-EfficientDet phone
fallback (YOLOv8m NOT exercised)**, **real YAMNet** on 1 s PCM chunks per student, SQLite persistence. Simulated browsers = threads calling the
routes through Flask's in-process client at the page's real rates (preview 2 fps, AI 1.25 fps, audio 1 Hz, one integrity event / 10 s) plus a
proctor polling every student's snapshot 1 Hz. Frames are small in-memory synthetic JPEGs → **accuracy is not measured**.
30 s measurement window per level (5 s warm-up). Environment: **1 vCPU / 4 GB**; CPU and RSS include the simulated clients.

| Students | Sessions ok/failed | HTTP 5xx | Exceptions | CPU avg / max % | RSS max MB |
|---|---|---|---|---|---|
| 1 | 1/0 | 0 | 0 | 10.3 / 15.0 | 1092.0 |
| 5 | 5/0 | 0 | 0 | 48.5 / 61.0 | 1144.1 |
| 10 | 10/0 | 0 | 0 | 95.0 / 101.0 | 1201.1 |
| 20 | 20/0 | 0 | 0 | 99.7 / 100.9 | 1320.8 |
| 30 | 30/0 | 0 | 0 | 99.7 / 100.8 | 1441.8 |

| Students | preview POST p50/p95 ms | AI POST p50/p95 ms | snapshot GET p50/p95 ms | frame age at serve p50/p95 ms | "capture→dashboard" p50/p95 ms | stale polls |
|---|---|---|---|---|---|---|
| 1 | 2.1 / 2.28 | 2.3 / 2.56 | 1.75 / 3.34 | 12.0 / 25.0 | 14.64 / 27.53 | 0/29 |
| 5 | 1.4 / 4.83 | 1.92 / 3.32 | 1.31 / 6.7 | 472.0 / 497.0 | 473.65 / 498.59 | 0/150 |
| 10 | 1.34 / 9.67 | 1.68 / 7.25 | 1.22 / 7.7 | 453.0 / 498.0 | 455.9 / 500.06 | 0/300 |
| 20 | 1.31 / 22.08 | 1.58 / 21.37 | 1.44 / 18.83 | 411.0 / 495.0 | 413.95 / 498.87 | 0/600 |
| 30 | 1.31 / 36.43 | 1.52 / 37.4 | 1.97 / 23.36 | 396.0 / 496.0 | 400.92 / 499.53 | 0/900 |

Reading the latency table: frame age ≈ the 500 ms preview interval (a frame is at most one interval old when served) — i.e. the live view
stays fresh at every level. "capture→dashboard" only counts frames the poller actually displayed, so it tracks frame age; the level-1 value is
a phase-lock artefact of two threads sleeping in step. A real browser adds network, JPEG decode and the 1 s tile poll on top.

| Students | AI fps/student | AI frames received | processed | replaced (dropped) | drop % | AI processing p50/p95 ms | AI queue delay p50/p95 ms | pool wait p95 ms |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.25 | 44 | 44 | 0 | 0 | 59.91 / 68.89 | 0.72 / 0.88 | 0.01 |
| 5 | 1.25 | 220 | 220 | 0 | 0 | 62.41 / 98.48 | 90.85 / 194.62 | 0.01 |
| 10 | 1.25 | 440 | 440 | 0 | 0 | 63.05 / 120.67 | 225.83 / 451.25 | 0.01 |
| 20 | 0.477 | 880 | 336 | 529 | 60 | 103.61 / 166.97 | 377.08 / 754.84 | 0.01 |
| 30 | 0.205 | 1313 | 217 | 1072 | 82 | 157.3 / 228.0 | 391.02 / 768.5 | 0.01 |

| Students | events lost (memory vs DB) | integrity events sent / in DB | wrong frames served | DB rows with wrong student/session | audio windows classified | audio errors |
|---|---|---|---|---|---|---|
| 1 | 0 | 3 / 3 | 0 of 29 | 0 | 35 | 0 |
| 5 | 0 | 15 / 15 | 0 of 150 | 0 | 175 | 0 |
| 10 | 0 | 28 / 28 | 0 of 300 | 0 | 350 | 0 |
| 20 | 0 | 56 / 56 | 0 of 600 | 0 | 697 | 0 |
| 30 | 0 | 82 / 82 | 0 of 900 | 0 | 1037 | 0 |

Workers: N session workers, **1** AI thread, **1** detector pair (pool size = CPU count = 1), scheduler ready-queue never exceeded N.
"Detector contention" is ≈ 0 because AI threads = pool size by design; the contention shows up as **AI queue delay and dropped frames**.

Interpretation (honest):
* Isolation, persistence and live-view freshness held at every level, including CPU saturation (VERIFIED for this configuration).
* **The analysis rate is the bottleneck**: on one core shared with the simulated clients, per-student AI rate falls from 1.25 fps
  (≤ 10 students) to 0.48 fps (20) and 0.2 fps (30) — a phone visible for < ~5 s could be missed at 30 students on this hardware.
* Derived estimate (arithmetic from the measured 60 ms/frame at N=1, **not a measurement**): 30 students × 1.25 fps × 60 ms ≈ 2.3 CPU-cores
  for face+phone (fallback backend) plus ≈ 0.75 core for YAMNet. **YOLOv8m costs are NOT MEASURED** and are expected to be much higher on CPU;
  size the server (GPU or more cores; `DETECTOR_POOL_SIZE`) on the target machine and re-run the harness there.
* **"Ready for 30 students in production" is NOT claimed.** PARTIALLY VERIFIED: correctness under 30 concurrent sessions VERIFIED; throughput on target
  hardware, real browsers/networks, YOLO cost, multi-hour endurance NOT TESTED.

---------------------------------------------------------------------------------------------------

## 11. Security

| Finding | Fix | TEST |
|---|---|---|
| `GET /api/sessions/<id>/report` readable by any logged-in user (IDOR) | owner student / owning proctor / admin only; missing and forbidden both → 404 | `test_session_report_idor_closed` |
| `/api/events`, `/api/sessions`, `/api/export/csv` returned all rooms to any proctor | scoped to owned rooms (admin: all) | `test_generic_api_scoped_to_owned_rooms` |
| `/proctor/students/poll` ignored room ownership | scoped, 403 for foreign room | `test_proctor_poll_and_streams_scoped` |
| SSE broadcast to all proctors | filtered by owned rooms | `test_sse_scoped_to_owned_rooms` |
| Stored XSS: client-controlled integrity `detail`, names, descriptions rendered via `innerHTML`; attribute-context injection in the join button / report buttons | server strips control chars/limits length; all dashboard interpolations escaped; `data-*` attributes instead of inline JS strings | `test_dashboards_escape_untrusted_strings`, `test_integrity_detail_is_bounded…` |
| CSV formula injection | `_csv_safe` on student/description/source columns | `test_csv_formula_injection_neutralised` |
| Open redirect via `?next=` | same-site relative paths only | `test_open_redirect_blocked_and_login_throttle` |
| No brute-force protection | 5 failures / 5 min per IP+user → 429 (process-local) | same test |
| Unvalidated uploads (video, frames, audio) | WebM magic-byte check; JPEG magic + 600 KB cap; audio 400 KB / sample-rate range; `MAX_CONTENT_LENGTH` (default 512 MB, `MAX_UPLOAD_MB`) | `test_video_upload_requires_webm…`, `test_frame_upload_validation`, `test_audio_upload_route…` |
| Arbitrary role strings via admin API | whitelist | `test_admin_role_validation…` |
| Public default `SECRET_KEY` | random key persisted (0600) in `instance/secret_key` unless `SECRET_KEY` env is set | `test_secret_key_is_not_the_public_default` |
| Missing hardening headers / cookie flags | `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`; `SameSite=Lax`, `HttpOnly`; `Secure` via `SESSION_COOKIE_SECURE=1` | `test_security_headers_present` |
| CSRF | **unchanged and still enforced** on the new binary endpoints; client retries once with a fresh token | `test_csrf_still_enforced_on_new_binary_endpoints` |

Preserved (verified by the existing suite + new tests): authentication, RBAC, session ownership, evidence file access control
(`/static/violations/*`, `/static/recordings/*` require ownership), path-traversal guards, SQLAlchemy ORM (no string-built SQL; the schema upgrade
uses fixed DDL strings only).
NOT TESTED / KNOWN LIMITATION: no CSP (the pages use the Tailwind and Font-Awesome CDNs and inline scripts); JWT is not used (session cookies);
login throttle and ownership cache are per-process; TLS termination is the deployer's job; the retention script (`scripts/retention_cleanup.py`) was not modified or run.

---------------------------------------------------------------------------------------------------

## 12. Database integrity

* New nullable columns `behavior_events.source / repeat_count / seq`; `ensure_schema()` adds them to older databases at startup
  (fixed DDL, idempotent, no data rewritten). **VERIFIED**: an old-schema DB gets the columns and keeps its rows (`test_schema_upgrade_of_a_previous_version_database`);
  the shipped `instance/proctor.db` (102 events) was migrated correctly on a real `python run.py` start (the package ships the *original* DB; it upgrades itself on first start).
* `exam_sessions.total_events` is incremented with an atomic SQL `UPDATE … SET total_events = total_events + 1` (previously read-modify-write
  from two threads). All event/snapshot/evidence writes go through one writer thread (FIFO: an evidence file is always written before the DB row that references it).
* Concurrency: 30 sessions × events/audio/preview/AI in parallel → memory count == DB count for every student, every row's `student_id`/`session_id`
  matches its worker, `total_events` equals the count (`test_concurrent_sessions_no_event_loss_no_contamination`, load test).
* EventBus and worker state are **process-local** (see §18). No Redis/Celery/WebRTC/Socket.IO was introduced.

---------------------------------------------------------------------------------------------------

## 13. Testing

> Superseded by §0 for the final numbers: after all changes the complete suite (legacy `test_all.py` + `test_smoke.py` + `tests/`) was run twice → **138 passed, 0 failed** both times. The per-suite table and history below describe earlier stages.

Commands: `python -m pytest -q` (runs `tests/`, `test_all.py`, `test_smoke.py`), `node tests/js/test_client.js`.

| Suite | Tests |
|---|---|
| `test_all.py`, `test_smoke.py` (existing, untouched) | 25 + 16 |
| `tests/test_event_risk_consistency.py` | 8 |
| `tests/test_video_stream.py` (freshness, stream status, stale, latest-frame, non-blocking preview, watchdog) | 9 |
| `tests/test_isolation_concurrency.py` (video / event / risk / audio / detector-state isolation, concurrent sessions, SSE scoping) | 5 |
| `tests/test_audio_pipeline.py` (real YAMNet) | 10 |
| `tests/test_security.py` | 16 |
| `tests/test_lan.py` (pacing, HTTPS certificate, CSRF/cookies over https from another host, run.py `--debug` refusal, page start-up order, no hard-coded localhost) | 8 |
| `tests/test_misc_infra.py` (schema upgrade, bus replay, class resolution, weights hash, no-dataset guard, benchmark/validator behaviour, metric arithmetic, Node helpers, admin runtime) | 15 |

Full-suite results (exact, final tree incl. the LAN changes of §19): `python -m pytest -q` twice in a row → **112 passed** (113 s) and **112 passed** (78 s);
`node tests/js/test_client.js` → all assertions passed; `python -m compileall` clean.
Counts per suite: 25 + 16 (legacy) + 8 + 9 + 5 + 10 + 16 + 15 + 8 = 112. (Before §19 the same suite had 104 tests and passed twice.)
Honest history: an earlier pair of runs gave 101 passed then 1 failed; the failure was a real defect (process-global ownership cache leaking between
apps that reuse the same numeric ids), fixed and covered by `test_ownership_cache_is_per_app_not_global`. A vacuous assertion that had hidden the
missing scheduler attachment was also found by review and strengthened. (Legacy tests no longer touch `instance/proctor.db`: see the root `conftest.py`.)
Test doubles (StubFace/StubPhone/StubPool, speech classifier stub) are used only for wiring; they are labelled and never used by a benchmark.
The final full-suite run and `python -m compileall` / import checks are recorded in the deliverable summary.

---------------------------------------------------------------------------------------------------

## 14. Remaining limitations (consolidated)

1. YOLOv8m runs (Linux/CPU) but **Windows is NOT VERIFIED** and **phone accuracy is NOT VERIFIED — REAL DATASET REQUIRED**.
2. **Audio accuracy NOT VERIFIED — REAL DATASET REQUIRED**; thresholds uncalibrated.
3. Browser behaviour (student page, dashboard, microphone/camera, CSRF refresh, session re-join) **NOT TESTED** in a real browser.
4. 30-student numbers are from **1 vCPU, MediaPipe fallback, in-process simulated clients**. AI rate degrades to 0.2 fps/student at 30. Re-measure on target hardware.
5. **Process-local state**: EventBus, replay ring, workers, DetectorPool, login throttle, ownership cache. Run **one server process with many threads**
   (`python run.py` / one Waitress or gunicorn process with `--threads`). Multiple processes (gunicorn `-w N`) would split students, SSE and pools — not supported.
6. Live "video" is 2 fps JPEG polling (tiles ≈ 1 fps); no MJPEG/WebRTC.
7. Face-touch signal is analytics only (no event/risk) by design.
8. Sustained-phone risk now grows faster than before (0.43 → 0.60 after 18 s) because the intended persistence weights now apply.
9. `modules/ml/classifier.py` (RF trained on synthetic data, thresholds 0.35/0.65) still produces `instant_risk`/anxiety diagnostics; it does not drive the displayed risk.
10. numpy: the project pins `numpy<2.0`; the audit ran numpy 2.4.4 + TF 2.21 (worked). On your machine follow `requirements.txt`; if pip cannot resolve TensorFlow with `numpy<2`, use a TF release that supports it (≥ 2.14, ≤ 2.17).
11. Evidence/recordings are stored on local disk; retention script untested; privacy/consent text unchanged.
12. `benchmark/load_test.py` (HTTP against a running server) was left as is; use `load_test_inprocess.py` for the reproducible in-process run.
13. Single-class fine-tuned YOLO has no `person` class → no multi-person detection with it.

---------------------------------------------------------------------------------------------------

## 15. Dataset requirements (nothing was downloaded, generated or simulated)

| Dataset | Folder | Contents | Used by |
|---|---|---|---|
| Phone | `datasets/phone_proctoring/` | `images/{train,val,test}/*.jpg|png` + `labels/{…}/*.txt` (YOLO: `0 xc yc w h`, empty file = hard negative); class `0: phone` | fine-tuning, `evaluate_phone_yolo.py`, `benchmark/phone_detection_benchmark.py` |
| Audio | `datasets/audio_proctoring/{train,val,test}/{silence,speech,whispering,shout,typing,background_noise,other}/*.wav` | mono clips, 1–3 s recommended | `audio_benchmark_real.py`, threshold calibration |

Each folder has a README (structure, formats, splits, how to validate/train/evaluate). `python training/dataset_status.py` reports what was found.
Empty-state behaviour (tested): benchmarks print `NO REAL DATA AVAILABLE — BENCHMARK NOT RUN` and **exit 0**; validators and `train_phone_yolo.py` exit 3 and refuse to train.
The previous synthetic artifacts were moved to `benchmark/legacy_synthetic/` with a warning README and must not be quoted as accuracy.

## 16. Training instructions (after you add data)

```
python training/dataset_status.py
python training/validate_phone_dataset.py
python training/train_phone_yolo.py --name phone_v1 --epochs 80 --batch 16 --imgsz 640      # never overwrites models/yolov8m.pt
python training/evaluate_phone_yolo.py --split test --weights runs/phone_finetune/phone_v1/weights/best.pt --out reports/phone_eval.json
```
To use the result, back up then replace `models/yolov8m.pt` (or set the weights path in `PhoneDetector`). Nothing was trained in this audit.

## 17. Benchmark instructions

```
python benchmark/phone_detection_benchmark.py --split test --out reports/phone_benchmark.json   # full pipeline: P/R/F1/FPR/FNR/latency/FPS (+ IoU-0.5 instance level)
python training/evaluate_phone_yolo.py --split test ...                                       # mAP50 / mAP50-95 (Ultralytics)
python training/validate_audio_dataset.py --check-decode
python training/audio_benchmark_real.py --split test --out reports/audio_benchmark.json
python benchmark/load_test_inprocess.py --levels 1 5 10 20 30 --duration 40                   # on the TARGET machine
```

## 18. Deployment limitations

* One process, many threads (§14.5). `DETECTOR_POOL_SIZE` ≈ physical cores (or 1 per GPU); raise cores/GPU before raising student count.
* Set `SECRET_KEY` (or keep the generated `instance/secret_key`), `SESSION_COOKIE_SECURE=1` behind HTTPS, `AUDIO_CONFIRM_HITS`, `AI_ASYNC=0` only for debugging.
* Start-up warms YAMNet in the background (first audio is classified once loaded; `/student/audio` reports `backend: "loading"` meanwhile).
* Install: `pip install -r requirements.txt` (TensorFlow ≈ 600 MB; Ultralytics pulls PyTorch).
* Admin-only `GET /admin/runtime` shows the live audio backend, load error, queues, event-bus counters and phone backend.


---------------------------------------------------------------------------------------------------

## 19. Multi-device / LAN operation (added after the first delivery)

Operating guide: **LAN_GUIDE.md**. Summary of what was inspected, changed and measured:

| Question | Finding | STATUS |
|---|---|---|
| Reachable from other devices? | `run.py` already bound `0.0.0.0` (threaded, no reloader); it printed a useless `http://0.0.0.0` URL — now prints the real LAN IPs | VERIFIED (real server run) |
| Camera/microphone from `http://<ip>:5000` | **Blocked by every browser** (secure-context rule). Fix: `python run.py --https` generates a self-signed certificate valid for localhost, 127.0.0.1, the computer name and all LAN IPs (`core/tls.py`), regenerated when the IP set changes | HTTPS server VERIFIED; browser behaviour with the warning page **NOT TESTED** |
| CORS | Not needed (same origin; no cross-origin calls, no hard-coded host in templates/JS/routes — asserted by a test) | VERIFIED |
| CSRF from another host | Enforced over HTTPS: no token → 400; token + same-origin Referer → OK; foreign Referer → 400 | VERIFIED (unit tests + curl against the running HTTPS server) |
| Cookies/login across devices | `Secure; HttpOnly; SameSite=Lax` (Secure is switched on automatically by `--https`); per-browser cookies; signing key persisted so restarts keep logins | VERIFIED (curl); real multi-browser **NOT TESTED** |
| Student page start-up | Camera/mic are now requested BEFORE a server session is created; clear English errors; red banner when the page is not HTTPS | syntax/static-order VERIFIED; **NOT TESTED in a browser** |
| Request load with many students | Per-student send rates are now chosen by the server (`core/pacing.py`): ≤10 students 2 fps preview / 1.25 fps AI, 11–20 → 1.4 / 0.8, >20 → 1 / 0.5 (audio chunks 2 s). Before this, a real-TLS run with 30 simulated students had 5 streams "stale" (3.4–4.1 s); after, 30 students passed 242/242 checks in two consecutive runs | PARTIALLY VERIFIED (1 vCPU, client and server sharing the core) |
| Real-network smoke test | `tools/lan_smoke_test.py` (real HTTPS, login, CSRF, cookies; simulated students; synthetic labelled frames): 2 / 5 / 10 / 20 / 30 students → 18 / 42 / 82 / 162 / 242 checks passed (LIVE, own-frame isolation, own-events isolation, explained risk, DB match) | VERIFIED for this environment |
| One process only | EventBus, workers, detector pool, replay ring are in-process memory → single process, many threads: `python run.py --https --port 5000` (never `gunicorn -w N`) | KNOWN LIMITATION |
| Same account on two devices | The second session replaces the first (workers are keyed by student id) → one account per device | KNOWN LIMITATION |
| Internet needed by browsers | Pages load Tailwind, Font Awesome, Chart.js and Google Fonts from CDNs | KNOWN LIMITATION — **offline behaviour NOT TESTED** |
| Exam recording | MediaRecorder default bitrate is ~1 GB/hour in browser RAM and above the 512 MB upload limit; capped to 500 kbps video + 64 kbps audio | change applied; **NOT TESTED in a browser** |
| `--debug` on the network | Refused (Werkzeug debugger = remote code execution) | VERIFIED (test) |

Latencies printed by the smoke test in the audit environment (~1.3 s per request at 30 students) are NOT network latencies: the simulated
students and the server shared one CPU core with TLS in pure Python. Do not quote them.
