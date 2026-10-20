# Architecture

## Request lifecycle (per student, per frame)

1. **Browser** captures a 320 × 240 JPEG from the webcam every 1.2 s and an
   RMS energy sample every 2 s. Frames are base64-encoded and POSTed to
   `/student/frame`; audio level + a coarse JS classification go to
   `/student/audio`.
2. **`SessionManager.process_frame()`** routes the frame to the per-student
   `StudentWorker`.
3. **`StudentWorker._run_pipeline()`** runs three modules:
   - `FaceAnalyzer.analyze(frame)` → MediaPipe iris + face-mesh →
     `{gaze, head_pitch, head_yaw, head_warning, attention_score,
       face_count, face_touching (head-bow proxy), gaze_deviation_secs}`
   - `PhoneDetector.detect(frame)` → 6-layer pipeline →
     `{phones, monitor, person_count, bypass_flags, quality}`
   - Latest audio result is merged in (browser RMS or YAMNet if enabled).
4. **`FeatureExtractor.update()`** ingests the three dicts into rolling
   30 s buffers and `FeatureExtractor.get_features()` emits the 14-dim
   vector consumed by the classifier.
5. **`BehaviorClassifier.predict()`** runs the RF pipeline →
   `{label, risk_score, risk_level, proba}`.
6. **Side effects:**
   - HUD overlay is drawn on the frame; the latest JPEG is stored as
     `self._snapshot_bytes` so the proctor's grid can pull it.
   - Every 5 s a `RiskSnapshot` row is persisted to the DB.
   - When throttle conditions are met, `BehaviorEvent` rows are persisted
     and pushed onto the SSE `EventBus`.
7. **Proctor dashboard** subscribes to `/proctor/events/stream` (SSE) and
   polls `/proctor/students` every few seconds. The grid is sorted by
   risk level (High → Low).

## Threads

- **Flask request threads** — handle HTTP. Tiny; they delegate immediately
  to the SessionManager.
- **Per-worker pipeline** — runs synchronously inside the request thread
  for that student. There is one *logical* worker per student but the
  pipeline itself is single-threaded; concurrency comes from independent
  students being processed in independent request threads.
- **DB-persistence threads** — fired with `threading.Thread(...).start()`
  for each event and risk snapshot so the request thread returns fast.
- **SSE generator threads** — one per connected proctor tab.
- **SessionManager watchdog** — daemon thread polling for idle students.

## Data model (SQLAlchemy)

```
User (1)──(N) ExamEnrollment (N)──(1) ExamRoom
User (1)──(N) ExamSession (N)──(1) ExamRoom
ExamSession (1)──(N) BehaviorEvent
ExamSession (1)──(N) RiskSnapshot
```

Schema lives in `db_models.py`. SQLite at `instance/proctor.db`.

## Why each component is in the design

| Component               | Why this and not the alternative |
|-------------------------|----------------------------------|
| MediaPipe Face Mesh     | Already runs in real time on a laptop CPU; published iris model gives sub-degree gaze without per-user calibration. |
| YOLOv8m (medium variant)| Sweet spot for phone class on COCO. The verifier + tracker layers compensate for false positives so we keep the YOLO score threshold low (0.15) and prioritise recall. |
| Random Forest           | Tabular, 14-feature input; RF handles heterogeneous units (degrees, frequencies, ratios, booleans) and gives calibrated `predict_proba` without temperature scaling. A neural net would not improve accuracy here and would be harder to defend. |
| Synthetic training data | Live human data collection was out of scope (proposal §5.4). Realistic class overlap was engineered into the generator so the model is not overfit to clean cluster centres. |
| YAMNet audio (local SavedModel) | Real AudioSet classifier loaded with `tf.saved_model.load` (no tensorflow_hub) and the official class map; contiguous 16 kHz PCM from the browser. If it cannot load, the analyser falls back to an explicitly labelled energy-variance heuristic and reports the exact reason. |
| SSE (not WebSocket)     | Proctor traffic is one-way (server → client). SSE is far simpler, plays nicely with Flask's `stream_with_context`, and survives reverse proxies that strip WebSocket frames. |

## Configuration knobs (`config.py`)

| Constant                | Meaning                                                    | Default |
|-------------------------|------------------------------------------------------------|---------|
| `FRAME_PROCESS_INTERVAL`| Min seconds between two processed frames per student       | 1.0     |
| `SNAPSHOT_INTERVAL`     | DB snapshot cadence (s)                                    | 5.0     |
| `EVENT_COOLDOWN`        | Min seconds between two events of the same type            | 8.0     |
| `PHONE_HOLD_SECS`       | Keep last phone detection alive for this many seconds      | 1.2     |
| `RISK_LOW_MAX` / `RISK_MEDIUM_MAX` | Score thresholds for Low / Medium / High        | 0.35 / 0.65 |
| `MAX_CONCURRENT_STUDENTS`| Soft cap on simultaneous workers                          | 30      |

All are environment-overridable.

## Failure modes and what happens

| Failure                          | Behaviour                                                                                                          |
|----------------------------------|--------------------------------------------------------------------------------------------------------------------|
| `yolov8m.pt` missing or stub     | Phone detector logs a clear warning and falls back to MediaPipe EfficientDet Lite; app still starts.               |
| `rf_classifier.pkl` missing      | `BehaviorClassifier` runs a rule-based fallback (defined in `_fallback_prediction`). App still starts.             |
| `tensorflow` missing             | `AudioAnalyzer` stays on the energy + variance backend (the default).                                              |
| `sounddevice` missing            | Server-side mic capture is disabled; browser-side audio still flows through `/student/audio`.                       |
| MediaPipe face models missing    | `FaceAnalyzer.__init__()` raises a `FileNotFoundError` with an exact `curl` command. The app cannot start without these — by design, face analysis is the core feature. |
| Network down at exam time        | Everything works. All inference is local once the weights are on disk.                                             |
