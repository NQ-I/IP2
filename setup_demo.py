"""
setup_demo.py — Creates demo accounts, exam rooms, and sample session data.

Run ONCE after initial setup:
    python setup_demo.py

Demo accounts:
  admin    / admin123    (admin role)
  proctor1 / proctor123  (proctor role)
  student1 … student5    / student123 (student role)

Demo room: CS401 (code: CS401A)
"""

import os, sys, uuid, datetime, random
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from extensions import db

STUDENTS = [
    ("student1", "Nasser Alqahtani",   "222428363"),
    ("student2", "Radi Alsadah",       "222422087"),
    ("student3", "Mazen Alshagawi",    "222402497"),
    ("student4", "Sara Al-Harbi",      "222401234"),
    ("student5", "Khalid Al-Otaibi",   "222405678"),
]


def run():
    app = create_app()
    with app.app_context():
        db.create_all()

        from db_models import User, ExamRoom, ExamEnrollment, ExamSession, BehaviorEvent, RiskSnapshot, ExamQuestion

        print("=" * 60)
        print("  AI Proctoring System — Demo Setup")
        print("=" * 60)

        # ── Create admin ──────────────────────────────────────────────
        _ensure_user("admin",    "admin123",    "admin@kfu.edu.sa",   "admin",
                     "System Administrator", "")
        print("  ✓ admin    / admin123    [admin]")

        # ── Create proctor ────────────────────────────────────────────
        _ensure_user("proctor1", "proctor123",  "proctor@kfu.edu.sa", "proctor",
                     "Dr. Raid Al-Alzubi",  "")
        print("  ✓ proctor1 / proctor123  [proctor]")

        # ── Create students ───────────────────────────────────────────
        for uname, fname, sid_no in STUDENTS:
            _ensure_user(uname, "student123", f"{uname}@student.kfu.edu.sa",
                         "student", fname, sid_no)
            print(f"  ✓ {uname:<10} / student123  [student]  — {fname}")

        # ── Create demo exam room ─────────────────────────────────────
        room_id = "CS401A"
        proctor = User.query.filter_by(username="proctor1").first()
        if not ExamRoom.query.get(room_id):
            room = ExamRoom(
                id           = room_id,
                name         = "CS401: Artificial Intelligence — Final Exam",
                subject      = "Artificial Intelligence",
                proctor_id   = proctor.id if proctor else None,
                duration_min = 60,
                status       = "waiting",
                max_students = 30,
            )
            db.session.add(room)
            db.session.commit()
            print(f"\n  ✓ Exam room created: {room_id}")
        else:
            print(f"\n  ✓ Exam room exists: {room_id}")

        # ── Enroll all students ───────────────────────────────────────
        for uname, _, _ in STUDENTS:
            u = User.query.filter_by(username=uname).first()
            if u:
                existing = ExamEnrollment.query.filter_by(room_id=room_id, student_id=u.id).first()
                if not existing:
                    db.session.add(ExamEnrollment(room_id=room_id, student_id=u.id))
        db.session.commit()
        print("  ✓ Students enrolled in CS401A")

        # ── Seed demo question bank ───────────────────────────────────
        if ExamQuestion.query.filter_by(room_id=room_id).count() == 0:
            DEMO_QUESTIONS = [
                ("mcq", "What does YOLOv8 stand for?",
                  [["a","You Only Look Once (version 8)"],
                   ["b","Yellow Optimised Learning Object"],
                   ["c","Your Own Local Output (v8)"]], "a", 1.0),
                ("mcq", "Which library is used for face landmark tracking in this system?",
                  [["a","TensorFlow Lite"],
                   ["b","Google MediaPipe Face Mesh"],
                   ["c","OpenCV Haarcascade"]], "b", 1.0),
                ("mcq", "What is the primary classification algorithm used for risk scoring?",
                  [["a","Support Vector Machine"],
                   ["b","Random Forest"],
                   ["c","K-Nearest Neighbors"]], "b", 1.0),
                ("mcq", "Which audio model detects speech and whispering events?",
                  [["a","Whisper by OpenAI"],
                   ["b","YAMNet (AudioSet)"],
                   ["c","DeepSpeech"]], "b", 1.0),
                ("mcq", "The system classifies student behaviour as:",
                  [["a","Cheating / Not Cheating (binary)"],
                   ["b","Focused / Anxious / Suspicious (probabilistic)"],
                   ["c","Pass / Fail / Retry"]], "b", 1.0),
                ("true_false",
                 "The system automatically blocks exams when cheating is detected.",
                  [["true","True"],["false","False"]], "false", 0.5),
                ("short_answer",
                 "Name the open-source object detector used in this system.",
                  [], "yolo", 1.0),
            ]
            for i, (qtype, text, opts, correct, marks) in enumerate(DEMO_QUESTIONS):
                q = ExamQuestion(room_id=room_id, order_index=i,
                                 qtype=qtype, text=text,
                                 correct_answer=correct, marks=marks)
                q.set_options(opts)
                db.session.add(q)
            db.session.commit()
            print(f"  ✓ Seeded {len(DEMO_QUESTIONS)} demo questions")
        else:
            print("  ✓ Question bank already populated")

        # ── Generate sample historical session data ───────────────────
        print("\n  Generating sample session data…")
        _generate_sample_sessions(app, room_id)

        print("\n" + "=" * 60)
        print("  Setup complete!")
        print()
        print("  Run the server:  python run.py")
        print("  Open:            http://localhost:5000")
        print()
        print("  Login as admin    → /admin/dashboard")
        print("  Login as proctor1 → /proctor/dashboard")
        print("  Login as student1 → /exam")
        print("=" * 60 + "\n")


def _ensure_user(username, password, email, role, full_name, student_id_no):
    from db_models import User
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, email=email, role=role,
                 full_name=full_name, student_id_no=student_id_no)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()


def _generate_sample_sessions(app, room_id):
    from db_models import User, ExamSession, BehaviorEvent, RiskSnapshot

    rng = random.Random(42)
    students = User.query.filter_by(role="student").all()

    EVENT_TEMPLATES = [
        ("gaze_deviation",   "Medium", 0.75, "Gaze: Looking Left for 6s"),
        ("head_movement",    "Low",    0.70, "Head pose: Head Down"),
        ("phone_detected",   "High",   0.85, "Mobile phone visible ≥2s"),
        ("multiple_persons", "High",   0.90, "Multiple persons detected (2)"),
        ("audio_speech",     "Medium", 0.60, "Suspicious audio: speech (60%)"),
        ("no_face",          "Medium", 0.90, "No face detected in frame"),
        ("gaze_deviation",   "Low",    0.65, "Gaze: Looking Right for 8s"),
        ("head_movement",    "Medium", 0.72, "Head pose: Head Up"),
    ]

    for student in students:
        session_id = str(uuid.uuid4())
        started    = datetime.datetime.utcnow() - datetime.timedelta(minutes=rng.randint(20,60))
        ended      = started + datetime.timedelta(minutes=rng.randint(10,50))

        # Risk profile varies by student
        risk_profiles = [0.1, 0.35, 0.55, 0.75, 0.9]
        base_risk = rng.choice(risk_profiles)
        if base_risk < 0.35:
            final_risk, final_label = "Low",    "Focused"
        elif base_risk < 0.65:
            final_risk, final_label = "Medium",  "Anxious"
        else:
            final_risk, final_label = "High",    "Suspicious"

        sess = ExamSession(
            id=session_id, room_id=room_id, student_id=student.id,
            started_at=started, ended_at=ended,
            final_risk=final_risk, final_score=round(base_risk,3),
            final_label=final_label,
        )
        db.session.add(sess)

        # Generate events
        n_events = rng.randint(1, 8) if base_risk > 0.3 else rng.randint(0,2)
        for i in range(n_events):
            etype, sev, conf, desc = rng.choice(EVENT_TEMPLATES)
            ts = started + datetime.timedelta(seconds=rng.randint(30, int((ended-started).total_seconds())-10))
            db.session.add(BehaviorEvent(
                session_id=session_id, student_id=student.id, room_id=room_id,
                timestamp=ts, event_type=etype, severity=sev, confidence=conf, description=desc,
            ))

        # Generate risk snapshots (every 5s)
        t = started
        while t < ended:
            noise = rng.uniform(-0.08, 0.08)
            score = max(0.0, min(1.0, base_risk + noise))
            lvl   = "Low" if score<0.35 else "Medium" if score<0.65 else "High"
            lbl   = "Focused" if lvl=="Low" else "Anxious" if lvl=="Medium" else "Suspicious"
            db.session.add(RiskSnapshot(
                session_id=session_id, student_id=student.id, room_id=room_id,
                timestamp=t, risk_score=round(score,3), risk_level=lvl, behavior_label=lbl,
            ))
            t += datetime.timedelta(seconds=5)

        sess.total_events = n_events
        sess.frames_processed = rng.randint(50, 400)

    db.session.commit()
    print(f"  ✓ Generated sample sessions for {len(students)} students")


if __name__ == "__main__":
    run()
