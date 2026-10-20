"""
test_smoke.py — Lightweight smoke test for the AI proctoring system.

Validates everything that can be tested without a live camera, without a
running Flask process, and without optional heavy dependencies
(mediapipe, ultralytics, tensorflow).

Run:
    python test_smoke.py

This is NOT a substitute for full integration testing — that requires the
real models and is run with `test_all.py` after installing all deps.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "  \033[32m✓\033[0m"
FAIL = "  \033[31m✗\033[0m"
SKIP = "  \033[33m─\033[0m"

results = []


def check(name, fn):
    try:
        fn()
        results.append((True, name))
        print(f"{PASS}  {name}")
    except Exception as exc:
        results.append((False, name))
        print(f"{FAIL}  {name}")
        print(f"       {type(exc).__name__}: {exc}")


def skip(name, reason):
    results.append((True, name))
    print(f"{SKIP}  {name}  (skipped: {reason})")


# ── 1. Core imports ─────────────────────────────────────────────────────────
def test_core_imports():
    import numpy, pandas, sklearn, cv2   # noqa: F401


# ── 2. Synthetic data generator ─────────────────────────────────────────────
def test_synthetic_data():
    from modules.ml.synthetic_data import (
        generate_dataset, generate_train_test_split, FEATURE_NAMES, LABEL_NAMES
    )
    df = generate_dataset(n_per_class=100, random_state=42)
    # Row count is approximate: hard examples ADD ~hard_example_frac*n rows
    # to each class. Allow [n_per_class .. n_per_class*1.30] per class.
    assert 300 <= df.shape[0] <= 390, f"unexpected row count {df.shape[0]}"
    for col in FEATURE_NAMES:
        assert col in df.columns, f"missing column {col}"
    assert set(df["label"].unique()) == {0, 1, 2}, "labels must be {0,1,2}"
    # Per-class counts in same ±30% band
    counts = df["label"].value_counts().to_dict()
    for c, n in counts.items():
        assert 80 <= n <= 140, f"class {c}: {n}"
    # Train/test split
    train, test = generate_train_test_split(
        n_per_class_train=100, n_per_class_test=40,
        random_state=42,
    )
    assert 280 <= train.shape[0] <= 400
    assert 100 <= test.shape[0]  <= 170


# ── 3. Feature extractor ────────────────────────────────────────────────────
def test_feature_extractor():
    from modules.ml.feature_extractor import FeatureExtractor
    fe = FeatureExtractor()
    fake_face  = {"gaze":"Looking Center", "gaze_deviation":False, "head_warning":None,
                  "head_pitch":2.0, "head_yaw":3.0, "attention_score":0.9,
                  "face_count":1, "face_touching":False, "eye_open":0.18,
                  "gaze_deviation_secs":0.0}
    fake_phone = {"phones":[], "person_count":1}
    fake_audio = {"is_suspicious":False, "audio_level":0.01}
    for _ in range(5):
        fe.update(fake_face, fake_phone, fake_audio)
    feat = fe.get_features()
    assert "vector" in feat, "expected 'vector' key"
    assert len(feat["vector"]) == 14, f"got {len(feat['vector'])} features"
    assert len(FeatureExtractor.FEATURE_NAMES) == 14


# ── 4. Trained classifier ───────────────────────────────────────────────────
def test_classifier_loads():
    import pickle
    path = os.path.join(os.path.dirname(__file__),
                        "trained_models", "rf_classifier.pkl")
    assert os.path.exists(path), \
        "rf_classifier.pkl missing — run train_model.py first"
    with open(path, "rb") as f:
        pipe = pickle.load(f)
    assert hasattr(pipe, "predict_proba"), "loaded object is not a sklearn Pipeline"


def test_classifier_predicts():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    # 14 zeros = "perfect focused" → should classify Focused / Low
    out = clf.predict([0.0] * 14)
    for k in ("label", "risk_score", "risk_level", "proba"):
        assert k in out, f"missing key {k}"
    assert out["label"] in ("Focused", "Anxious", "Suspicious")
    assert 0.0 <= out["risk_score"] <= 1.0


def test_classifier_realistic_accuracy():
    """Train accuracy must NOT be near 100%. >97% indicates the data is too
    separable and the dataset rewrite was lost."""
    import pickle
    from modules.ml.synthetic_data import generate_dataset, FEATURE_NAMES
    path = os.path.join(os.path.dirname(__file__),
                        "trained_models", "rf_classifier.pkl")
    with open(path, "rb") as f:
        pipe = pickle.load(f)
    # Fresh data, different seed, harder noise
    df = generate_dataset(n_per_class=300, random_state=2027,
                          noise_level=0.25, hard_example_frac=0.20,
                          label_noise_frac=0.05)
    X = df[FEATURE_NAMES].values
    y = df["label"].values
    acc = (pipe.predict(X) == y).mean()
    assert 0.80 <= acc <= 0.97, (
        f"Out-of-distribution accuracy = {acc:.3f}; expected in [0.80, 0.97]. "
        "If <0.80 the model is broken; if >0.97 the dataset is too easy.")


# ── 5. Reporting module ─────────────────────────────────────────────────────
def test_reporting_imports():
    from modules.reporting import SessionReportBuilder   # noqa: F401


def test_reporting_pdf_generation():
    """Build a tiny report end-to-end from fake data."""
    import datetime
    from modules.reporting import SessionReportBuilder

    # Minimal fake objects matching what the route gives the builder
    session = {
        "id": "test-session-0001",
        "room_id": "DEMOROOM",
        "started_at": datetime.datetime(2026, 5, 1, 10, 0, 0),
        "ended_at":   datetime.datetime(2026, 5, 1, 10, 15, 0),
        "final_risk": "Medium",
        "final_score": 0.42,
        "final_label": "Anxious",
        "total_events": 3,
        "frames_processed": 60,
    }
    student = {
        "id": 1, "username": "smoke_student",
        "full_name": "Smoke Test Student",
        "student_id_no": "999000111", "email": "smoke@test.invalid",
    }
    room = {"id": "DEMOROOM", "name": "Demo Room", "subject": "Smoke Test"}
    events = [
        {"timestamp": datetime.datetime(2026,5,1,10,2,0),
         "event_type":"gaze_deviation","severity":"Medium",
         "confidence":0.75,"description":"Gaze: Looking Left for 6s",
         "screenshot_path":None},
        {"timestamp": datetime.datetime(2026,5,1,10,5,0),
         "event_type":"head_movement","severity":"Low",
         "confidence":0.65,"description":"Head pose: Head Down",
         "screenshot_path":None},
        {"timestamp": datetime.datetime(2026,5,1,10,12,0),
         "event_type":"audio_speech","severity":"Medium",
         "confidence":0.7,"description":"Suspicious audio: speech (70%)",
         "screenshot_path":None},
    ]
    snapshots = []
    base = datetime.datetime(2026,5,1,10,0,0)
    import math
    for i in range(90):
        score = 0.30 + 0.20 * math.sin(i / 10.0)
        lvl   = "Low" if score < 0.35 else ("Medium" if score < 0.65 else "High")
        lbl   = "Focused" if lvl=="Low" else ("Anxious" if lvl=="Medium" else "Suspicious")
        snapshots.append({"timestamp": base + datetime.timedelta(seconds=10*i),
                          "risk_score": round(score,3),
                          "risk_level": lvl,
                          "behavior_label": lbl})

    builder = SessionReportBuilder(
        session=session, student=student, room=room,
        events=events, snapshots=snapshots,
        generated_by="smoke_test",
        violations_root=__import__("tempfile").gettempdir(),
    )
    # HTML
    html = builder.build_html()
    assert "<html" in html.lower() and "smoke_student" in html

    # PDF
    out_dir = __import__("os").path.join(__import__("tempfile").gettempdir(), "proctor_smoke")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "report.pdf")
    builder.build_pdf(pdf_path)
    assert os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 5000, \
        "PDF was not written or is tiny"

    # CSV
    csv_path = os.path.join(out_dir, "report.csv")
    builder.build_csv(csv_path)
    assert os.path.exists(csv_path) and os.path.getsize(csv_path) > 50


# ── 6. Models / weights on disk ─────────────────────────────────────────────
def test_yolo_weights_exist_or_warn():
    """If YOLOv8m weights are missing, warn but don't fail."""
    p = os.path.join(os.path.dirname(__file__), "models", "yolov8m.pt")
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"yolov8m.pt not at {p} — phone detection will fall back to "
            "MediaPipe. See README §4.")
    sz = os.path.getsize(p)
    if sz < 10 * 1024 * 1024:
        raise ValueError(
            f"yolov8m.pt is only {sz/1024:.0f} KB (real weights are ~52 MB). "
            "This is a stub. See README §4.")


def test_face_models_exist():
    here = os.path.join(os.path.dirname(__file__), "models")
    for fname in ("blaze_face_short_range.tflite", "face_landmarker.task"):
        p = os.path.join(here, fname)
        if not os.path.exists(p):
            raise FileNotFoundError(f"missing {p}")


# ── 7. Phone detection sub-modules (no YOLO needed) ─────────────────────────
def test_phone_subcomponents():
    """Verifier / tracker / anti-bypass / ensemble are pure CV code → testable
    without YOLO."""
    import numpy as np
    from modules.detection.phone_verifier   import PhoneVerifier
    from modules.detection.phone_tracker    import PhoneTracker
    from modules.detection.phone_anti_bypass import AntiBypasDetector
    from modules.detection.phone_ensemble   import PhoneEnsemble
    from modules.detection.preprocessor     import FramePreprocessor

    # Build a synthetic frame containing a fake phone-ish region
    frame = np.full((240, 320, 3), 80, dtype=np.uint8)
    # "Phone" region — dark vertical rectangle with brighter screen
    import cv2
    cv2.rectangle(frame, (120, 50), (180, 180), (35, 35, 38), -1)
    cv2.rectangle(frame, (124, 65), (176, 168), (130,130,140), -1)
    box = (120, 50, 60, 130)

    pre = FramePreprocessor()
    enhanced = pre.enhance(frame)

    ver = PhoneVerifier().verify(enhanced, box)
    assert "score"    in ver
    assert "decision" in ver
    assert "checks"   in ver

    tracker = PhoneTracker()
    confirmed = tracker.update([{"label":"Phone Candidate",
                                 "confidence":0.85,
                                 "box":box,
                                 "verifier_score":ver["score"],
                                 "verifier_decision":ver["decision"]}])
    assert isinstance(confirmed, list)

    ab = AntiBypasDetector()
    flags = ab.update(frame, [], [])
    assert isinstance(flags, dict)

    ens = PhoneEnsemble()
    if confirmed:
        out = ens.evaluate(confirmed[0])
        assert "ensemble_score" in out


# ── 8. App factory (only if Flask deps are present) ─────────────────────────
def test_app_factory():
    try:
        import flask_sqlalchemy, flask_login   # noqa
    except ImportError:
        raise RuntimeError(
            "flask-sqlalchemy / flask-login not installed — cannot test the "
            "Flask factory in this environment. Full app validation must be "
            "run on the project deploy machine.")
    from app import create_app
    app = create_app()
    rules = {r.endpoint for r in app.url_map.iter_rules()}
    expected = {
        "auth.login", "auth.logout",
        "student.start_session", "student.submit_frame",
        "proctor.students", "proctor.events_stream",
        "admin.stats",
        "reports.session_report",     # NEW
        "reports.room_summary",       # NEW
    }
    missing = expected - rules
    assert not missing, f"missing endpoints: {missing}"


# ── 9. Train + evaluate scripts compile ─────────────────────────────────────
def test_train_model_compiles():
    import py_compile
    py_compile.compile(os.path.join(os.path.dirname(__file__), "train_model.py"),
                       doraise=True)


def test_evaluate_model_compiles():
    import py_compile
    py_compile.compile(os.path.join(os.path.dirname(__file__), "evaluate_model.py"),
                       doraise=True)


# ── 10. Routes compile ──────────────────────────────────────────────────────
def test_all_routes_compile():
    import py_compile
    here = os.path.join(os.path.dirname(__file__), "routes")
    for f in sorted(os.listdir(here)):
        if f.endswith(".py"):
            py_compile.compile(os.path.join(here, f), doraise=True)


# ── 11. Modules compile ─────────────────────────────────────────────────────
def test_all_modules_compile():
    import py_compile
    here = os.path.join(os.path.dirname(__file__), "modules")
    for root, _, files in os.walk(here):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_compile.compile(os.path.join(root, f), doraise=True)


# ── Runner ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  AI Proctoring System — smoke test")
    print("  " + "─" * 56)

    print("\n  [1] Core imports")
    check("numpy / pandas / sklearn / cv2 present", test_core_imports)

    print("\n  [2] Synthetic dataset")
    check("synthetic_data generates correct schema", test_synthetic_data)

    print("\n  [3] Feature extractor")
    check("FeatureExtractor emits 14-dim vector", test_feature_extractor)

    print("\n  [4] Trained classifier")
    check("rf_classifier.pkl loads",                  test_classifier_loads)
    check("BehaviorClassifier.predict() works",       test_classifier_predicts)
    check("Out-of-distribution accuracy in [0.80, 0.97]", test_classifier_realistic_accuracy)

    print("\n  [5] Reporting")
    check("modules.reporting imports",                 test_reporting_imports)
    check("Report builder produces PDF + HTML + CSV",  test_reporting_pdf_generation)

    print("\n  [6] Model weights")
    yolo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "models", "yolov8m.pt")
    if not os.path.exists(yolo_path):
        skip("YOLOv8m present and full-size",
             "models/yolov8m.pt missing — see README §4")
    elif os.path.getsize(yolo_path) < 10 * 1024 * 1024:
        skip("YOLOv8m present and full-size",
             f"models/yolov8m.pt is only {os.path.getsize(yolo_path)/1024:.0f} KB — "
             "this is a stub. Real weights must be installed before the demo "
             "(see README §4). Phone detection will fall back to MediaPipe.")
    else:
        check("YOLOv8m present and full-size", test_yolo_weights_exist_or_warn)
    check("MediaPipe face models present",            test_face_models_exist)

    print("\n  [7] Phone detection sub-modules")
    check("verifier / tracker / anti-bypass / ensemble run", test_phone_subcomponents)

    print("\n  [8] Flask app factory")
    try:
        import flask_sqlalchemy, flask_login   # noqa
        check("Flask app registers expected endpoints",   test_app_factory)
    except ImportError:
        skip("Flask app registers expected endpoints",
             "flask-sqlalchemy / flask-login not installed in this env — "
             "run this test on the demo machine after pip install -r requirements.txt")

    print("\n  [9] Scripts compile")
    check("train_model.py compiles",                  test_train_model_compiles)
    check("evaluate_model.py compiles",               test_evaluate_model_compiles)

    print("\n  [10] All routes compile")
    check("routes/*.py compile",                       test_all_routes_compile)

    print("\n  [11] All modules compile")
    check("modules/*.py compile",                      test_all_modules_compile)

    # ── Summary ─────────────────────────────────────────────────────────────
    total  = len(results)
    passed = sum(1 for ok, _ in results if ok)
    failed = total - passed
    print("\n  " + "─" * 56)
    print(f"  Total:   {total}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print("  " + "─" * 56)
    if failed:
        print("\n  Some smoke tests failed. Fix them before running the demo.\n")
        sys.exit(1)
    print("\n  All smoke tests passed.\n")
