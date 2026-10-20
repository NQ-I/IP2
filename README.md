# AI Online Exam Proctoring System
### King Faisal University — College of Computer Sciences and IT
#### CS Graduation Project — May 2026

**Team**
- Nasser Alqahtani (222428363)
- Radi Alsadah (222422087)
- Mazen Alshagawi (222402497)

**Supervisor:** Dr. Raid Mohammad Alzubi

---

## 1 — What this system does

A multi-student real-time online proctoring platform. It watches a student
through their built-in webcam and microphone, extracts behavioural features
on the server using established pre-trained models, and assigns each session
a **probabilistic** risk profile (Focused / Anxious / Suspicious) rather than
a binary cheater / non-cheater label. The proctor sees a live grid of every
active student; the instructor receives a full session report after the
exam.

The system does **not** automatically punish students. It is an assistive
tool that surfaces high-risk cases for human review. This positioning is
explicitly required by the project proposal (§1.5).

---

## 2 — Module overview

| Layer                | Technology                       | Role |
|----------------------|----------------------------------|------|
| Face & gaze analysis | MediaPipe Face Mesh              | Iris-based gaze direction, head pose, attention scoring, face counting |
| Object detection     | YOLOv8m (6-layer pipeline)       | Phone detection with temporal tracking and anti-bypass; multi-person count |
| Audio anomaly        | YAMNet (local SavedModel) + labelled fallback | Live path: the browser streams contiguous 16 kHz Int16 PCM (~1 s chunks) to `/student/audio`; a per-student 3 s buffer is classified on one inference thread by the shared `AudioAnalyzer` (`modules/detection/audio_analyzer.py`), which runs the **local** YAMNet SavedModel in `models/yamnet/` with the official class map (`tf.saved_model.load`, no `tensorflow_hub`). If TensorFlow/model/class map cannot load, the backend is the clearly labelled `"energy-variance fallback"` and the exact reason is in `AudioAnalyzer.status()` / admin `GET /admin/runtime`. Suspicious classes (speech / whispering / shout) become normalized events and risk through the same funnel as every other detector. **Accuracy on real audio is NOT VERIFIED — REAL DATASET REQUIRED** — see AUDIT_REPORT_FINAL.md §6. |
| Behavioural ML       | Random Forest (200 trees)        | Trained and loaded at runtime; contributes the `proba`/label *nuance* returned by `predict_hybrid()`, but the live **cheating-risk number itself is computed by the deterministic rule engine only** (`modules/ml/classifier.py:predict_hybrid`, `score = rule`). The RF's own `risk_score` is exposed in telemetry as `rf_score` for comparison, not used in the risk decision. See §3 for why. |
| Backend              | Flask + SQLAlchemy (SQLite)      | Role-based auth, REST API, SSE event bus |
| Frontend             | Tailwind + Chart.js              | Admin / Proctor / Student dashboards |
| Reporting            | matplotlib + reportlab           | Per-session HTML / PDF / CSV instructor reports |

---

## 3 — Honest metrics (synthetic evaluation)

The Random Forest is trained on a synthetic dataset that simulates the
14-feature vector emitted by the live pipeline. We **deliberately** designed
the dataset with realistic class overlap so the reported metrics are
defensible rather than perfect.

**The RF is not on the final cheating-risk decision path.** `BehaviorClassifier.predict_hybrid()`
computes an RF score (`rf`) and a separate deterministic rule score (`rule`)
from live signals (phone, extra person, integrity violations, sustained
gaze-away, audio), then sets `score = rule` — the RF's score is returned
alongside as `rf_score` for observability/telemetry only and does not affect
`risk_score`, `risk_level`, or the Suspicious/Anxious/Focused label. This was
a deliberate engineering decision (the RF is out-of-distribution on
early/sparse frame windows and produced a "risk frozen at ~30%" bug), not an
oversight — but earlier revisions of this README described the system as
using RF output in the live risk number, which was inaccurate. If you want
the RF back in the risk-decision loop, retrain it on real session windows
(not synthetic data) and blend it with a bounded weight rather than the
current `max`-and-then-`rule`-only approach.

| Metric                    | Value      |
|---------------------------|------------|
| Test accuracy (held-out, noisier) | **90.84%** |
| 5-fold cross-validation   | **92.34% ± 0.36%** |
| Per-class FPR (Focused / Anxious / Suspicious) | 4.3% / 6.7% / 2.7% |
| ROC-AUC (Focused / Anxious / Suspicious)       | 0.972 / 0.933 / 0.974 |
| Inference latency (single predict_proba)       | ~13.5 ms / call |

Why these numbers are credible:

- **Test set is harder than train.** A separate test set is generated with a
  different RNG seed (`+7919`), higher feature noise, and more "hard
  examples" — focused students who happen to be restless, anxious students
  who look calm, etc. Reporting the test accuracy is honest because the
  model never saw any of those rows.
- **Confusion matrix shows the right error pattern.** Most errors are
  Focused ↔ Anxious (the classes that genuinely overlap behaviourally), and
  Focused ↔ Suspicious errors are near zero — which is critical because
  *those* errors would be false accusations of cheating.
- **Per-class FPR is well below the proposal's 10% target** (§6.4), with
  particular attention to keeping the Focused → Suspicious confusion rate
  near zero.

Re-run the evaluation any time with:

```bash
python evaluate_model.py
```

This produces `benchmark/model_evaluation_report.html`, JSON results, and
five PNG charts under `benchmark/figs/`.

---

## 4 — Quick start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. YOLOv8m weights: models/yolov8m.pt is ALREADY shipped with the project (52 MB) - nothing to download.
#    Check that Ultralytics can load it (real inference test on sample photos bundled in the package):
python -m pytest tests/test_real_yolo.py -q

# 3. (Optional) re-train the Random Forest on the synthetic generator (~30 s). A trained model is already shipped
#    (trained_models/rf_classifier.pkl, built with scikit-learn 1.7.2 - keep that version).
python train_model.py

# 4. Seed demo accounts and the demo room (or use tools/create_test_users.py for a LAN test)
python setup_demo.py

# 5. Start the server (single process)
python run.py
```

Open `http://localhost:5000` in a browser (same computer only). For student laptops on the LAN use HTTPS — see **LAN_GUIDE.md**.

If you skip step 2 the system still runs — phone detection falls back to
the lighter MediaPipe object detector and the startup banner prints a
clear warning. **The demo will not crash because of a missing model.**

### Demo accounts

| Username   | Password   | Role    | Lands on                |
|------------|------------|---------|-------------------------|
| `admin`    | `admin123` | Admin   | `/admin/dashboard`      |
| `proctor1` | `proctor123`| Proctor | `/proctor/dashboard`    |
| `student1` … `student5` | `student123` | Student | `/exam`         |

Demo room: `CS401A` — CS401: Artificial Intelligence Final Exam.

---

## 5 — Architecture

```
                       Browser (student)
                              │
                  base64 JPEG frames + audio RMS
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                       Flask app (app.py)                       │
│  /auth/*  /student/*  /proctor/*  /admin/*  /reports/*         │
│                              │                                  │
│                       SessionManager                            │
│                              │                                  │
│             ┌────────────────┼────────────────┐                │
│             ▼                ▼                ▼                │
│        StudentWorker 1  StudentWorker 2  …Worker N             │
│        ┌─────────────┐                                          │
│        │ FaceAnalyzer│  ← MediaPipe FaceMesh                   │
│        │ PhoneDetector│ ← YOLOv8m + 5 post-layers              │
│        │ AudioAnalyzer│ ← energy + variance                    │
│        │ FeatureExtractor (14-dim sliding window)              │
│        │ BehaviorClassifier (RF pipeline)                      │
│        └─────────────┘                                          │
│                              │                                  │
│                              ▼                                  │
│        SQLite ⇆ Events / RiskSnapshots / Sessions / Users      │
│                              │                                  │
│                          EventBus (SSE)                         │
└──────────────────────────────│─────────────────────────────────┘
                               ▼
                       Proctor dashboard
                  (live grid + alert feed +
                   per-student detail + reports)
```

The complete deployment matches the proposal's Component Diagram (§6.2)
and Deployment Diagram (§8).

---

## 6 — Reporting

After (or during) a session, a proctor or admin can export a full
**Instructor Analytics Report** for any student. Three formats are
supported:

- **PDF**  — printable, includes KPI strip, risk timeline chart, behaviour
  distribution charts, severity breakdown, full event log, and rule-based
  recommendations.
- **HTML** — same content as PDF, web-viewable, charts embedded as base64
  PNG so it works as a single self-contained file.
- **CSV**  — raw event log, suitable for further analysis.

Routes:

```
GET /reports/session/<session_id>?format=html|pdf|csv
GET /reports/room/<room_id>/summary?format=html|csv
```

From the proctor dashboard, open any student's detail modal and click
**Export Report** to choose a format.

Every report ends with a disclaimer matching the proposal's §1.5
positioning: the system is *assistive*; it does not declare a student a
cheater on its own.

---

## 7 — Files of note

```
exam_proctor/
├── app.py                      Flask app factory + role-based routing
├── run.py                      Production entry point with prerequisite checks
├── setup_demo.py               Creates demo users, room, sample sessions
├── train_model.py              Trains the RF classifier on the synthetic dataset
├── evaluate_model.py           Honest evaluation pipeline → benchmark report
├── config.py                   SECRET_KEY, DB URL, thresholds, intervals
├── extensions.py               db, login_manager singletons
├── db_models.py                User, ExamRoom, ExamSession, BehaviorEvent, RiskSnapshot
│
├── core/
│   ├── session_manager.py      Manages all concurrent StudentWorkers (≤30)
│   ├── student_worker.py       Per-student AI pipeline orchestration
│   └── event_bus.py            Thread-safe SSE fan-out
│
├── modules/
│   ├── detection/
│   │   ├── face_analyzer.py    MediaPipe FaceMesh (gaze, head pose, attention)
│   │   ├── phone_detector.py   YOLO + verifier + tracker + anti-bypass + ensemble
│   │   ├── phone_verifier.py   8-check secondary classifier (Layer 3)
│   │   ├── phone_tracker.py    IoU-based temporal multi-frame tracker (Layer 4)
│   │   ├── phone_anti_bypass.py Bypass-pattern detector (Layer 5)
│   │   ├── phone_ensemble.py   Weighted confidence combiner (Layer 6)
│   │   ├── audio_analyzer.py   Energy + variance detector (YAMNet upgrade docs)
│   │   ├── preprocessor.py     CLAHE, sharpening, brightness normalisation
│   │   └── phone_benchmark.py  Standalone benchmark harness
│   ├── ml/
│   │   ├── feature_extractor.py  Rolling 30-s window → 14-feature vector
│   │   ├── synthetic_data.py     Realistic-overlap dataset generator
│   │   └── classifier.py         RF Pipeline (StandardScaler + RandomForest)
│   ├── reporting/
│   │   ├── __init__.py
│   │   └── session_report.py     PDF / HTML / CSV builder
│   └── utils/camera.py
│
├── routes/
│   ├── auth.py                 /auth/login, /register, /logout
│   ├── api.py                  /api/stats/summary, /api/events, /api/sessions
│   ├── api_student.py          /student/session/start|stop, /student/frame, /student/audio
│   ├── api_proctor.py          /proctor/students, /proctor/events/stream (SSE), rooms
│   ├── api_admin.py            /admin/stats, /admin/users
│   ├── api_reports.py          /reports/session/<id>?format=pdf|html|csv
│   └── stream.py               Legacy single-user MJPEG fallback
│
├── templates/
│   ├── admin/dashboard.html
│   ├── proctor/dashboard.html  Live grid + detail modal + export menu
│   ├── student/exam.html       Webcam capture + risk gauge + alerts
│   ├── login.html
│   └── register.html
│
├── models/                     Pre-trained model weights (download once)
│   ├── yolov8m.pt              ⚠ ~52 MB — install separately (see Quick start)
│   ├── blaze_face_short_range.tflite
│   ├── face_landmarker.task
│   └── efficientdet_lite0.tflite
│
├── trained_models/
│   └── rf_classifier.pkl       Produced by `python train_model.py`
│
├── benchmark/
│   ├── model_evaluation_report.html  Produced by `python evaluate_model.py`
│   ├── model_evaluation_results.json
│   ├── figs/*.png
│   ├── phone_benchmark_report.html   Produced by phone_detection_benchmark.py
│   └── phone_detection_benchmark.py
│
└── instance/proctor.db         SQLite database (auto-created)
```

---

## 8 — Limitations (read this before the defense)

These are honest, documented limitations of the current implementation:

- **The Random Forest is trained on synthetic data.** No live human dataset
  was collected — the proposal (§5.4) justifies this on privacy and
  scope-of-work grounds. The 91% accuracy is an upper bound on what the
  classifier achieves *on the simulated distribution*; real students may
  produce features outside that distribution.
- **Audio uses the local YAMNet SavedModel when TensorFlow is installed** (`models/yamnet/`, official 521-class map in
  `models/yamnet/assets/`). If TensorFlow, the model or the class map cannot be loaded, the backend is the explicitly labelled
  "energy-variance fallback" and the exact reason is in `AudioAnalyzer.status()["load_error"]` / admin `GET /admin/runtime`. YAMNet accuracy on real
  exam audio is NOT VERIFIED (no real audio dataset); the decision thresholds are uncalibrated defaults.
- **The "face_touching" feature is a head-bow proxy.** MediaPipe Face Mesh
  does not track hands, so we cannot detect literal hand-to-face contact
  from the video stream. The feature uses nose-tip Y position to detect a
  bowed head — a coarse stress indicator. The variable name has been
  documented in code; users should read it as "head bowed / stress" not
  "hand touched face".
- **No automatic exam blocking.** Per proposal §1.5, the system never
  blocks an exam or accuses a student. It surfaces risk levels for human
  review only. Every exported report says so in its footer.
- **Single-camera, laptop-only.** Multi-camera setups (proposal §2 review)
  are out of scope.

---

## 9 — Acknowledgements

This work was carried out at the College of Computer Sciences and IT, King
Faisal University, under the supervision of Dr. Raid Mohammad Alzubi.

The system uses the following open-source projects:
Ultralytics YOLOv8, Google MediaPipe, scikit-learn, Flask, Tailwind CSS,
Chart.js, matplotlib, ReportLab.


---

## Phase 7 audit (final)

**Status of the final audit (what is verified and what is not): AUDIT_REPORT_FINAL.md §0.**  Historical change logs: `docs/history/` (superseded).

**Multi-device (LAN) operation: LAN_GUIDE.md** (`python run.py --https`, then open `https://<server-ip>:5000/exam` on each student laptop).

Read **AUDIT_REPORT_FINAL.md** first: bugs found/fixed, the detection → event → risk → dashboard pipeline, live-video design,
measured 1/5/10/20/30-student results, security fixes, and every limitation with an explicit status.

```
pip install -r requirements.txt
python run.py --port 5000
python -m pytest -q                      # tests/ + test_all.py + test_smoke.py
node tests/js/test_client.js             # browser-side helpers (DOM-free)
python training/dataset_status.py        # what real data was found + next commands
python benchmark/load_test_inprocess.py --levels 1 5 10 20 30 --duration 40   # run on the TARGET machine
```
