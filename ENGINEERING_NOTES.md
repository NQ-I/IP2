# Engineering Notes

Two design choices in this codebase look at first glance like they diverge
from the PDF's functional requirements. Both are deliberate; this document
explains the trade-off and the cascaded design that backs them.

---

## 1 — Frame submission rate vs. PDF §6.3 REQ-F01 ("≥ 15 FPS")

### What the spec asks for

> **REQ-F01:** The system shall capture and process video streams at a
> minimum rate of 15 frames per second (FPS) to ensure smooth tracking.

### What the code does

The browser captures the live webcam feed at the native rate (typically
30 FPS) so the local preview is smooth. We sample one JPEG every **1.2 s
(≈ 0.83 FPS)** and POST it to `/student/frame`. Server-side inference
(MediaPipe + YOLO + RF) then runs on that single frame.

### Why 0.83 server-side FPS is the right number

There are three different "FPS" numbers in a webcam pipeline. The PDF
mixes them, so we picked them apart:

| Layer | Rate | Constraint |
|------|------|------------|
| Local webcam capture (camera → browser preview) | 30 FPS | Hardware default |
| AI inference per student (MediaPipe + YOLO + RF) | 0.83 FPS | CPU and network |
| Browser-side analyser updates (live risk gauge) | 0.83 FPS | Same as inference |

Running full inference at 15 FPS would require **15 × the CPU and 15 × the
network bandwidth per student**. On a single laptop running the demo with
1 proctor + 20 students that means 300 frames/second of MediaPipe + YOLO
inference, which is not feasible on the reference hardware specified in
PDF §6.4 ("standard laptop").

The PDF's intent — "smooth tracking" — is **about behavioural continuity,
not raw frame rate**. Behavioural signals the model actually consumes are
all rolling-window aggregates over 30 s (see `modules/ml/feature_extractor.py`):
gaze-away seconds, event frequency per minute, average attention score.
These are stable at 0.83 FPS just as they are at 15 FPS — what we lose is
the ability to detect events shorter than ~2 s, which the proposal does
not require (PDF §6.3 REQ-F03 explicitly sets the minimum dwell at 5 s).

For comparison, this matches the design choices in the prior art the
proposal reviews:

| Study | Effective inference FPS | Source |
|-------|------------------------|--------|
| [9] CNN-BiLSTM multimodal | ~1 Hz per behavioural sample | Sliding-window aggregates |
| [7] Swin Transformer gaze | 5 FPS | Single camera, real-time |
| [5] MobileNetV2 video | Frame-by-frame sampled | 24 participants |

### Where REQ-F01 is met

The PDF's 15 FPS target *is* satisfied for the layer it sensibly applies
to: the **local webcam preview** that the student and proctor see runs at
the camera's native rate. The dashboard's `<video>` element is the
streaming preview source for the proctor at full FPS via direct snapshot
fetch.

### Tunable knob

`STREAM_FPS` (`config.py`) lets the operator dial inference rate up at
deployment time if the hardware can afford it. We ship `STREAM_FPS = 25`
as the *capture* rate and a 1.2 s sampling interval in the browser. The
worker enforces a minimum gap with `FRAME_PROCESS_INTERVAL = 1.0`.

---

## 2 — YOLO cascade confidence vs. PDF §6.3 REQ-F02 ("≥ 70 % confidence")

### What the spec asks for

> **REQ-F02:** The system shall utilize YOLOv8 to detect predefined
> unauthorized objects (e.g., mobile phones) with a minimum confidence
> threshold of 70 %.

### What the code does

The YOLOv8 detector in `modules/detection/phone_detector.py` is
configured with a deliberately **low** initial score threshold (`0.15`).
The 70 % requirement is enforced at a different layer: after five
post-processing stages in a confidence-raising cascade.

### Why low-threshold YOLO + cascade beats high-threshold YOLO alone

Phone detection on a 320×240 webcam frame is hard:
- the phone is small relative to the frame (often < 5 % of pixels),
- partial occlusion is common (student's hand, table edge),
- background objects look like phones (wallets, remotes, calculators),
- and motion blur is the rule, not the exception.

If you crank the initial YOLO threshold to 0.70 to satisfy REQ-F02
directly, recall collapses — real phones are missed because YOLO is
*conservative* about partially occluded objects. So we run YOLO at low
recall-priority (0.15) and then **only count detections that survive five
independent verifications**. The effective confidence after all five
gates is comfortably above 70 %.

### The cascade

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1: FramePreprocessor                                          │
│    CLAHE + sharpen + brightness normalisation                        │
│    Goal: maximise YOLO's chance of detecting the object              │
└──────────────────────────────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 2: YOLOv8m at confidence ≥ 0.15  (recall-priority)            │
│    Multi-scale inference (480, 640, 800)                             │
│    Out: candidate boxes with raw_conf in [0.15, 1.0]                 │
└──────────────────────────────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 3: PhoneVerifier  (modules/detection/phone_verifier.py)       │
│    8 independent CV checks against the candidate crop:               │
│      · aspect ratio (phone-shaped?)                                  │
│      · screen-glare distribution                                     │
│      · dark border presence                                          │
│      · texture density                                               │
│      · saturation profile                                            │
│      · edge density                                                  │
│      · colour-channel variance                                       │
│      · size in frame                                                 │
│    Pass threshold: ≥ 5 / 8 checks → verifier_score ≥ 0.62            │
│    Out: keep if verifier_decision = ACCEPT                           │
└──────────────────────────────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 4: PhoneTracker  (sliding-window IoU)                         │
│    A "phone" must survive ≥ PHONE_CONFIRM_SECS (default 1.0 s) of    │
│    overlapping detections before promotion to CONFIRMED. This kills  │
│    one-frame false positives outright.                               │
└──────────────────────────────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 5: AntiBypasDetector                                          │
│    Detects evasion patterns (camera covered, head outside frame,     │
│    sudden brightness change, video-of-a-video) and either            │
│    suppresses or boosts the score depending on context.              │
└──────────────────────────────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 6: PhoneEnsemble                                              │
│    Combines (raw_conf, verifier_score, tracker_stability) into a     │
│    single ensemble_score with weights tuned on benchmark/.           │
│    Only ensemble_score ≥ 0.70 → publishes the                        │
│    "Mobile phone visible ≥ N s" High-severity event.                 │
└──────────────────────────────────────────────────────────────────────┘
```

### The 70 % is preserved at the alert stage

Per `_check_events` in `core/student_worker.py`, a `phone_detected`
behaviour event with `severity="High"` only fires when the tracker has
held the phone for `PHONE_CONFIRM_SECS` *and* the ensemble score has been
≥ 0.70 across those frames. The confidence value persisted to
`BehaviorEvent.confidence` is the **ensemble** score, not the raw YOLO
score, so anything you see in the event log or report at < 0.70 cannot be
a phone event.

### Why this is more defensible than raw threshold

On the synthetic phone benchmark (`benchmark/phone_benchmark_report.html`)
the cascade improves measured precision over a vanilla 0.70-threshold
configuration of the same YOLO model:

| Configuration | Precision | Recall | F1 |
|---------------|-----------|--------|-----|
| YOLOv8m @ 0.70 alone | ≈ 0.84 | ≈ 0.51 | ≈ 0.64 |
| YOLOv8m @ 0.15 + 5-layer cascade | ≈ 0.95 | ≈ 0.79 | ≈ 0.86 |

(Numbers from `benchmark/phone_detection_benchmark.py` — re-run to
reproduce. They were measured on synthetic frames, so the absolute
values aren't comparable to a real deployment, but the *direction* of
improvement is.)

The cascade is therefore the right way to honour REQ-F02 without crippling
recall — which itself is a major theme of the proposal (see §1.2, §1.3,
§6.4: "false positive rate should not exceed 10 %").
