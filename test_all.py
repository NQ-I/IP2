"""
test_all.py — Full system test suite.
Tests: imports, ML pipeline, API endpoints, multi-user concurrency, DB integrity.

Run:  python test_all.py
"""
import os, sys, time, json, threading, uuid, io
sys.path.insert(0, os.path.dirname(__file__))

PASS = "  ✓"; FAIL = "  ✗"; WARN = "  ⚠"
results = []; warnings_list = []


def check(name, fn):
    try:
        fn(); results.append((True, name)); print(f"{PASS}  {name}")
    except Exception as exc:
        results.append((False, name))
        print(f"{FAIL}  {name}"); print(f"       {type(exc).__name__}: {exc}")


def warn(name, fn):
    try:
        fn(); print(f"{PASS}  {name}")
    except Exception as exc:
        warnings_list.append(name)
        print(f"{WARN}  {name} (optional): {type(exc).__name__}: {str(exc)[:60]}")


# ────────────────────────────────────────────────────────────────────
print("=" * 60)
print("  AI Proctoring System — Full Test Suite")
print("=" * 60)

# ── 1. Imports ───────────────────────────────────────────────────────
print("\n[1] Core imports")
check("numpy",         lambda: __import__("numpy"))
check("scikit-learn",  lambda: __import__("sklearn"))
check("pandas",        lambda: __import__("pandas"))
check("Flask",         lambda: __import__("flask"))
check("Flask-Login",   lambda: __import__("flask_login"))
warn("OpenCV",         lambda: __import__("cv2"))
warn("MediaPipe",      lambda: __import__("mediapipe"))
warn("ultralytics",    lambda: __import__("ultralytics"))

# ── 2. ML modules ────────────────────────────────────────────────────
print("\n[2] ML modules")

def test_synthetic():
    from modules.ml.synthetic_data import generate_dataset, FEATURE_NAMES
    n_per_class = 30
    df = generate_dataset(n_per_class=n_per_class)
    # generate_dataset() intentionally adds borderline "hard example" rows
    # beyond the 3 base classes (see its hard_example_frac param, default
    # 0.18) to give the classifier realistic class overlap instead of
    # perfectly separable synthetic data. The old assertion
    # (`len(df) == n_per_class * 3`) predated that design and didn't
    # account for the extra hard-example rows — it was failing on
    # correct, intentional behavior, not a bug in generate_dataset. Fixed
    # to compute the same total the function itself documents.
    n_hard_groups = 4  # focused/anxious, anxious/focused, anxious/suspicious, suspicious/anxious
    expected = n_per_class * 3 + n_hard_groups * int(n_per_class * 0.18)
    assert len(df) == expected, f"expected {expected} rows, got {len(df)}"
    assert len(FEATURE_NAMES) == 14
    assert set(df["label"].unique()) == {0, 1, 2}

def test_feature_extractor():
    from modules.ml.feature_extractor import FeatureExtractor
    fe = FeatureExtractor()
    face  = {"gaze":"Looking Center","gaze_deviation":False,"gaze_deviation_secs":0,
             "head_pitch":0,"head_yaw":0,"head_warning":None,"eye_open":0.2,
             "face_touching":False,"attention_score":0.9,"face_count":1,"face_boxes":[]}
    phone = {"phones":[],"person_count":1}
    audio = {"event":"silence","confidence":0,"is_suspicious":False,"audio_level":0.0}
    fe.update(face, phone, audio)
    feat = fe.get_features()
    assert len(feat["vector"]) == 14
    assert 0.0 <= feat["avg_attention"] <= 1.0

def test_classifier_focused():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    vec = [1.0,0.5,0.0,0.0,0.2,1.0,3.0,3.0,0.90,5.0,0.22,0.05,0.0,5.0]
    r   = clf.predict(vec)
    assert r["label"] == "Focused"
    assert r["risk_level"] == "Low"
    assert 0.0 <= r["risk_score"] <= 0.35

def test_classifier_suspicious():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    vec = [15.0,10.0,5.0,3.0,6.0,4.0,20.0,20.0,0.20,120.0,0.15,0.8,1.0,10.0]
    r   = clf.predict(vec)
    assert r["label"] == "Suspicious"
    assert r["risk_level"] == "High"
    assert r["risk_score"] >= 0.65

def test_classifier_anxious():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    vec = [4.0,3.0,0.0,0.0,1.0,2.0,8.0,8.0,0.60,25.0,0.20,0.15,0.0,8.0]
    r   = clf.predict(vec)
    assert r["label"] in ("Anxious","Focused","Suspicious")  # transition zone
    assert "proba" in r
    assert abs(sum(r["proba"].values())-1.0) < 0.01

def test_classifier_proba():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    vec = [5.0,5.0,1.0,0.0,2.0,1.0,10.0,10.0,0.55,30.0,0.20,0.20,0.0,7.0]
    r   = clf.predict(vec)
    assert "proba" in r
    assert all(k in r["proba"] for k in ("Focused","Anxious","Suspicious"))

check("Synthetic dataset",     test_synthetic)
check("FeatureExtractor",      test_feature_extractor)
check("Classifier — Focused",  test_classifier_focused)
check("Classifier — Suspicious",test_classifier_suspicious)
check("Classifier — Anxious",  test_classifier_anxious)
check("Classifier — probas",   test_classifier_proba)

# ── 3. Risk thresholds ───────────────────────────────────────────────
print("\n[3] Risk scoring thresholds")

def test_risk_levels():
    from modules.ml.classifier import BehaviorClassifier
    clf = BehaviorClassifier()
    low_vec  = [1.0,0.5,0.0,0.0,0.0,0.5,2.0,2.0,0.95,2.0,0.25,0.01,0.0,3.0]
    high_vec = [20.0,15.0,8.0,4.0,8.0,6.0,25.0,25.0,0.10,180.0,0.10,1.0,1.0,15.0]
    r_low  = clf.predict(low_vec)
    r_high = clf.predict(high_vec)
    assert r_low["risk_level"]  == "Low"
    assert r_high["risk_level"] == "High"
    assert r_low["risk_score"]  < r_high["risk_score"]

check("Low vs High risk separation", test_risk_levels)

# ── 4. Event bus ─────────────────────────────────────────────────────
print("\n[4] Event bus (SSE)")

def test_event_bus():
    from core.event_bus import EventBus
    bus = EventBus()
    q   = bus.subscribe()
    bus.push({"type":"test","msg":"hello"})
    time.sleep(0.05)
    item = q.get_nowait()
    d    = json.loads(item)
    assert d["type"] == "test"
    assert d["msg"]  == "hello"
    bus.unsubscribe(q)
    assert bus.subscriber_count() == 0

def test_event_bus_fanout():
    from core.event_bus import EventBus
    bus = EventBus()
    qs  = [bus.subscribe() for _ in range(5)]
    bus.push({"type":"fanout","n":42})
    time.sleep(0.05)
    for q in qs:
        item = q.get_nowait()
        d    = json.loads(item)
        assert d["n"] == 42
        bus.unsubscribe(q)

check("EventBus push/subscribe", test_event_bus)
check("EventBus fan-out (5 subs)", test_event_bus_fanout)

# ── 5. Database ──────────────────────────────────────────────────────
print("\n[5] Database models")

def test_db_create():
    from app import create_app
    from config import Config
    app = create_app(Config)
    with app.app_context():
        from extensions import db
        from sqlalchemy import inspect
        db.create_all()
        tables = inspect(db.engine).get_table_names()
        required = {"users","exam_rooms","exam_enrollments","exam_sessions",
                    "behavior_events","risk_snapshots"}
        missing = required - set(tables)
        assert not missing, f"Missing tables: {missing}"

def test_db_user_crud():
    from app import create_app
    from config import Config
    app = create_app(Config)
    with app.app_context():
        from db_models import User
        from extensions import db
        uname = f"_test_{uuid.uuid4().hex[:8]}"
        u = User(username=uname, email=f"{uname}@test.com", role="student")
        u.set_password("testpass123")
        db.session.add(u); db.session.commit()
        loaded = User.query.filter_by(username=uname).first()
        assert loaded is not None
        assert loaded.check_password("testpass123")
        assert not loaded.check_password("wrongpass")
        db.session.delete(loaded); db.session.commit()

check("DB — all tables exist", test_db_create)
check("DB — User CRUD + password hash", test_db_user_crud)

# ── 6. Flask routes ──────────────────────────────────────────────────
print("\n[6] Flask HTTP routes")

def make_test_client():
    from app import create_app
    from config import Config

    class TestConfig(Config):
        # Phase 5 fix: previously this pointed at the REAL project database
        # (instance/proctor.db). The security regression tests create real
        # throwaway users/rooms/sessions and were never cleaned up, so every
        # test run permanently polluted the shipped database with orphaned
        # accounts (confirmed: 26 -> 56 users accumulated across this
        # session's repeated test runs). An isolated in-memory SQLite DB
        # per test-app instance fixes this at the root rather than adding
        # per-test teardown code, and is the standard Flask-SQLAlchemy
        # testing pattern.
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False
        TESTING = True

    app = create_app(TestConfig)
    with app.app_context():
        from extensions import db
        db.create_all()
    return app.test_client(), app

def test_health():
    c, _ = make_test_client()
    r = c.get("/admin/health")
    assert r.status_code == 200
    d = json.loads(r.data)
    assert d["status"] == "ok"

def test_login_redirect():
    c, _ = make_test_client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 401)

def test_login_post():
    c, app = make_test_client()
    with app.app_context():
        from db_models import User
        from extensions import db
        uname = f"_tlogin_{uuid.uuid4().hex[:6]}"
        u = User(username=uname, email=f"{uname}@t.com", role="student")
        u.set_password("Password99!")
        db.session.add(u); db.session.commit()
    r = c.post("/auth/login", data={"username":uname,"password":"Password99!"},
               follow_redirects=False)
    assert r.status_code in (302, 200)

def test_student_endpoints_unauthed():
    c, _ = make_test_client()
    for path in ["/student/rooms", "/student/status"]:
        r = c.get(path)
        assert r.status_code in (302, 401, 403), f"{path} should require auth"

def test_proctor_endpoints_unauthed():
    c, _ = make_test_client()
    r = c.get("/proctor/students")
    assert r.status_code in (302, 401, 403)

def test_api_events_unauthed():
    c, _ = make_test_client()
    r = c.get("/api/events")
    assert r.status_code in (302, 401)


def test_proctor_cannot_access_unowned_student():
    """Regression test for the Phase 1/2 IDOR fix: a proctor with no room
    assigned to a given student must be refused (403), not served that
    student's live status/report."""
    c, app = make_test_client()
    with app.app_context():
        from db_models import User, ExamRoom
        from extensions import db
        tag = uuid.uuid4().hex[:6]
        owner   = User(username=f"_pown_{tag}", email=f"_pown_{tag}@t.com", role="proctor")
        owner.set_password("Password99!")
        outsider = User(username=f"_pout_{tag}", email=f"_pout_{tag}@t.com", role="proctor")
        outsider.set_password("Password99!")
        student = User(username=f"_stu_{tag}", email=f"_stu_{tag}@t.com", role="student")
        student.set_password("Password99!")
        db.session.add_all([owner, outsider, student]); db.session.commit()

        room = ExamRoom(id=f"room_{tag}", name="Room", subject="CS",
                        proctor_id=owner.id, duration_min=60, status="active")
        db.session.add(room); db.session.commit()

        from db_models import ExamEnrollment
        db.session.add(ExamEnrollment(room_id=room.id, student_id=student.id))
        db.session.commit()
        student_id = student.id

    c.post("/auth/login", data={"username": f"_pout_{tag}",
                                "password": "Password99!"})
    r = c.get(f"/proctor/student/{student_id}/status")
    assert r.status_code == 403, (
        f"outsider proctor should be refused, got {r.status_code}")

    # Second client for the SAME app/in-memory DB (independent cookie jar,
    # shared database) rather than a second make_test_client() call, which
    # would now create a completely separate isolated in-memory database
    # (see the Phase 5 fix to make_test_client()) and could never see the
    # owner/room/student created above.
    c2 = app.test_client()
    c2.post("/auth/login", data={"username": f"_pown_{tag}",
                                 "password": "Password99!"})
    r2 = c2.get(f"/proctor/student/{student_id}/status")
    # The student has no live worker running in this test (no frames were
    # ever submitted), so the correct response for an authorized-but-offline
    # student is 404 ("Student not active"), not 403. What this asserts is
    # narrower and more important: ownership must NOT be the reason for any
    # rejection here.
    assert r2.status_code != 403, (
        f"owning proctor should not be blocked by ownership, got 403")
    assert r2.status_code in (200, 404), (
        f"unexpected status for owning proctor: {r2.status_code}")


def test_student_cannot_upload_video_to_other_session():
    """Regression test for the Phase 2 IDOR fix: a student must not be able
    to attach/overwrite a video recording on another student's session by
    passing an arbitrary session_id."""
    c, app = make_test_client()
    with app.app_context():
        from db_models import User, ExamSession
        from extensions import db
        import datetime as _dt
        tag = uuid.uuid4().hex[:6]
        victim  = User(username=f"_vic_{tag}", email=f"_vic_{tag}@t.com", role="student")
        victim.set_password("Password99!")
        attacker = User(username=f"_atk_{tag}", email=f"_atk_{tag}@t.com", role="student")
        attacker.set_password("Password99!")
        db.session.add_all([victim, attacker]); db.session.commit()
        sess = ExamSession(id=str(uuid.uuid4()), student_id=victim.id,
                           started_at=_dt.datetime.utcnow())
        db.session.add(sess); db.session.commit()
        sess_id = sess.id

    c.post("/auth/login", data={"username": f"_atk_{tag}",
                                "password": "Password99!"})
    r = c.post("/student/session/video",
              data={"session_id": sess_id,
                    "video": (io.BytesIO(b"fake webm bytes"), "evil.webm")},
              content_type="multipart/form-data")
    assert r.status_code == 403, (
        f"attacker should be refused, got {r.status_code}: {r.data}")


check("GET /admin/health",              test_health)
check("GET / redirects to login",       test_login_redirect)
check("POST /auth/login valid user",    test_login_post)
check("Student endpoints need auth",    test_student_endpoints_unauthed)
def test_csrf_protection():
    """Phase 5 regression test: verifies CSRF is actually enforced when NOT
    in the test-only disabled mode (make_test_client() disables it for
    every other test in this file, which is the standard, accepted
    Flask-WTF testing pattern — this test deliberately re-enables it to
    prove the protection is real)."""
    from app import create_app
    from config import Config
    import re
    app = create_app(Config)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = True   # deliberately ON for this test
    c = app.test_client()

    r = c.post("/auth/login", data={"username": "nope", "password": "nope"})
    assert r.status_code == 400, f"missing CSRF token should be rejected, got {r.status_code}"

    r_bad = c.post("/auth/login", data={"username": "nope", "password": "nope",
                                        "csrf_token": "garbage-invalid-token"})
    assert r_bad.status_code == 400, f"invalid CSRF token should be rejected, got {r_bad.status_code}"

    r_get = c.get("/auth/login")
    m = re.search(rb'name="csrf_token" value="([^"]+)"', r_get.data)
    assert m, "login page should render a csrf_token field"
    token = m.group(1).decode()
    r_ok = c.post("/auth/login", data={"username": "nope", "password": "nope",
                                       "csrf_token": token})
    assert r_ok.status_code != 400, (
        f"a valid CSRF token should not be rejected as a CSRF failure, got {r_ok.status_code}")


check("Proctor endpoints need auth",    test_proctor_endpoints_unauthed)
check("API events needs auth",          test_api_events_unauthed)
check("[SECURITY] proctor blocked from unowned student",
     test_proctor_cannot_access_unowned_student)
check("[SECURITY] student blocked from uploading to others' session",
     test_student_cannot_upload_video_to_other_session)
check("[SECURITY] CSRF protection enforced (missing/invalid/valid token)",
     test_csrf_protection)

# ── 7. Concurrency ───────────────────────────────────────────────────
print("\n[7] Concurrency & thread safety")

def test_event_bus_concurrent():
    from core.event_bus import EventBus
    bus   = EventBus()
    q     = bus.subscribe()
    count = 100
    errs  = []
    def pusher():
        for i in range(count):
            try: bus.push({"i":i})
            except Exception as e: errs.append(e)
    threads = [threading.Thread(target=pusher) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errs, f"{len(errs)} push errors"
    bus.unsubscribe(q)

def test_feature_extractor_concurrent():
    from modules.ml.feature_extractor import FeatureExtractor
    from modules.ml.classifier import BehaviorClassifier
    errors = []
    clf = BehaviorClassifier()
    def worker(tid):
        try:
            fe   = FeatureExtractor()
            face = {"gaze":"Center","gaze_deviation":False,"gaze_deviation_secs":0,
                    "head_pitch":0,"head_yaw":0,"head_warning":None,"eye_open":0.2,
                    "face_touching":False,"attention_score":0.9,"face_count":1,"face_boxes":[]}
            ph   = {"phones":[],"person_count":1}
            au   = {"event":"silence","confidence":0,"is_suspicious":False,"audio_level":0.0}
            for _ in range(20):
                fe.update(face,ph,au)
                feat = fe.get_features()
                r    = clf.predict(feat["vector"])
                assert r["label"] in ("Focused","Anxious","Suspicious")
        except Exception as e:
            errors.append((tid, e))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, f"Errors: {errors}"

check("EventBus concurrent push (5 threads × 100)",   test_event_bus_concurrent)
check("Classifier concurrent predict (10 threads × 20)", test_feature_extractor_concurrent)

# ── 8. Model file ────────────────────────────────────────────────────
print("\n[8] Trained model")

def test_model_file():
    path = os.path.join("trained_models","rf_classifier.pkl")
    assert os.path.exists(path), "Run: python train_model.py"
    import pickle
    with open(path,"rb") as f:
        m = pickle.load(f)
    import numpy as np
    vec = np.array([[1.0,0.5,0.0,0.0,0.2,1.0,3.0,3.0,0.90,5.0,0.22,0.05,0.0,5.0]])
    pred = m.predict(vec)
    assert pred[0] in (0,1,2)

check("rf_classifier.pkl valid", test_model_file)

# ── 9. Cross-student isolation (Phase 6 scalability refactor) ──────────
print("\n[9] Cross-student detector-state isolation")

def test_cross_student_isolation():
    """Phase 6 mandatory regression test: FaceAnalyzer/PhoneDetector are now
    borrowed from a small shared pool (core/detector_pool.py) instead of
    one private instance per student, to fix the memory blowup measured in
    Phase 4 (peak RSS 3.58/3.9GB at 30 students). Both classes hold real
    per-student mutable state (gaze calibration/smoothing, phone-track
    history) — this test proves concurrent students hammering the pool
    never end up sharing that state, even in the worst case (pool size 1
    on this single-core sandbox, so every student's frames are serialized
    through the exact same underlying detector pair)."""
    import numpy as np, cv2, base64, threading
    from flask import Flask
    from core.student_worker import StudentWorker

    app = Flask(__name__)
    n_students, frames_per = 6, 20

    def make_frame_b64(seed):
        rng = np.random.RandomState(seed)
        img = rng.randint(60, 180, (240, 320, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    workers = [StudentWorker(student_id=9000 + i, session_id=f"iso_s{i}",
                             room_id="iso_room", student_name=f"IsoStudent{i}",
                             violations_dir=__import__("tempfile").gettempdir(), app=app)
              for i in range(n_students)]
    frames = [make_frame_b64(5000 + i) for i in range(n_students)]
    errors = []

    def hammer(idx):
        for _ in range(frames_per):
            try:
                workers[idx].process_frame(frames[idx])
            except Exception as exc:
                errors.append(f"student{idx}: {type(exc).__name__}: {exc}")

    # The wall-clock budget scales with the REAL per-frame cost.  It was a flat 60 s, written against the
    # MediaPipe fallback (~35 ms/frame); with the YOLOv8m backend (~0.6-0.8 s/frame on 1 vCPU) the 120
    # serialized frames legitimately need ~90 s.  A real deadlock (a thread that never finishes) still fails.
    t0 = time.time(); workers[0].process_frame(frames[0]); per_frame = max(time.time() - t0, 0.05)
    budget = max(60.0, 3.0 * n_students * frames_per * per_frame)
    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(n_students)]
    for t in threads: t.start()
    deadline = time.time() + budget
    for t in threads: t.join(timeout=max(0.1, deadline - time.time()))
    for t in threads:
        assert not t.is_alive(), "a student's frame processing hung (possible deadlock in the pool)"

    assert not errors, f"errors during concurrent processing: {errors[:5]}"

    face_ids  = {id(w._face_state) for w in workers}
    phone_ids = {id(w._phone_state) for w in workers}
    tracker_ids    = {id(w._phone_state["_tracker"]) for w in workers}
    antibypass_ids = {id(w._phone_state["_antibypass"]) for w in workers}
    assert len(face_ids) == n_students, "FACE STATE LEAKED BETWEEN STUDENTS"
    assert len(phone_ids) == n_students, "PHONE STATE LEAKED BETWEEN STUDENTS"
    assert len(tracker_ids) == n_students, "PHONE TRACKER LEAKED BETWEEN STUDENTS"
    assert len(antibypass_ids) == n_students, "ANTIBYPASS STATE LEAKED BETWEEN STUDENTS"

check("[SCALABILITY] cross-student detector-state isolation (6 concurrent students)",
     test_cross_student_isolation)


def test_cross_student_video_isolation():
    """Phase 6 mandatory regression test (section 23): proves the fast
    preview-frame path (update_preview_frame/get_snapshot, added to
    decouple the proctor's live view from AI-inference latency) never
    lets one student's frame appear under another student's identity —
    each student's frame carries a distinct pixel marker and must decode
    back to exactly that student's marker, never another's."""
    import numpy as np, cv2, base64, threading, time
    from flask import Flask
    from core.student_worker import StudentWorker

    app = Flask(__name__)
    n_students = 8

    def make_marked_frame_b64(marker_byte):
        img = np.full((240, 320, 3), marker_byte, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    workers = [StudentWorker(student_id=9200 + i, session_id=f"vid_v{i}",
                             room_id="vid_vroom", student_name=f"VidStudent{i}",
                             violations_dir=__import__("tempfile").gettempdir(), app=app)
              for i in range(n_students)]
    errors = []

    def hammer(idx):
        marker = 10 + idx * 20
        frame = make_marked_frame_b64(marker)
        for _ in range(15):
            try:
                workers[idx].update_preview_frame(frame)
            except Exception as exc:
                errors.append(f"student{idx}: {exc}")
            time.sleep(0.01)

    threads = [threading.Thread(target=hammer, args=(i,)) for i in range(n_students)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)
    assert not errors, f"errors during concurrent preview updates: {errors}"

    mismatches = []
    for i, w in enumerate(workers):
        expected_marker = 10 + i * 20
        snap = w.get_snapshot()
        assert snap is not None, f"student {i} has no snapshot at all"
        arr = cv2.imdecode(np.frombuffer(snap, np.uint8), cv2.IMREAD_COLOR)
        actual_marker = int(arr[0, 0, 0])
        if abs(actual_marker - expected_marker) > 5:  # allow JPEG quantization
            mismatches.append((i, expected_marker, actual_marker))
    assert not mismatches, f"CROSS-STUDENT VIDEO CONTAMINATION: {mismatches}"

check("[LIVE VIDEO] cross-student video isolation (8 concurrent students)",
     test_cross_student_video_isolation)

# ── Summary ──────────────────────────────────────────────────────────
passed = sum(1 for ok,_ in results if ok)
total  = len(results)
failed = [n for ok,n in results if not ok]

print(f"\n{'='*60}")
print(f"  Tests:    {passed}/{total} passed")
if warnings_list: print(f"  Optional: {len(warnings_list)} skipped ({', '.join(warnings_list[:3])}…)")
if failed:
    print(f"  FAILED:")
    for n in failed: print(f"    ✗  {n}")
print("=" * 60 + "\n")
if failed: sys.exit(1)
