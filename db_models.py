"""db_models.py — Full multi-student proctoring platform schema."""
import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(64),  unique=True, nullable=False, index=True)
    email          = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash  = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(16),  default="student")
    full_name      = db.Column(db.String(128), default="")
    student_id_no  = db.Column(db.String(32),  default="")
    created_at     = db.Column(db.DateTime,    default=datetime.datetime.utcnow)
    is_active      = db.Column(db.Boolean,     default=True)
    sessions    = db.relationship("ExamSession",    backref="student", lazy="dynamic", foreign_keys="ExamSession.student_id")
    enrollments = db.relationship("ExamEnrollment", backref="student", lazy="dynamic", foreign_keys="ExamEnrollment.student_id")
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)
    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email,
                "role": self.role, "full_name": self.full_name,
                "student_id_no": self.student_id_no,
                "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")}
    def __repr__(self): return f"<User {self.username} [{self.role}]>"

@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

class ExamRoom(db.Model):
    __tablename__ = "exam_rooms"
    id           = db.Column(db.String(16),  primary_key=True)
    name         = db.Column(db.String(128), nullable=False)
    subject      = db.Column(db.String(64),  default="")
    proctor_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    duration_min = db.Column(db.Integer, default=60)
    status       = db.Column(db.String(16), default="waiting")
    max_students = db.Column(db.Integer, default=30)
    proctor      = db.relationship("User", foreign_keys=[proctor_id])
    enrollments  = db.relationship("ExamEnrollment", backref="room", lazy="dynamic")
    sessions     = db.relationship("ExamSession", backref="room", lazy="dynamic", foreign_keys="ExamSession.room_id")
    def to_dict(self):
        return {"id": self.id, "name": self.name, "subject": self.subject,
                "status": self.status, "duration_min": self.duration_min,
                "max_students": self.max_students,
                "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "proctor_id": self.proctor_id,
                "proctor": self.proctor.username if self.proctor else None,
                "proctor_name": self.proctor.username if self.proctor else "–",
                "enrolled_count": self.enrollments.count(),
                "enrolled_students": [e.student_id for e in self.enrollments]}

class ExamEnrollment(db.Model):
    __tablename__ = "exam_enrollments"
    id         = db.Column(db.Integer, primary_key=True)
    room_id    = db.Column(db.String(16), db.ForeignKey("exam_rooms.id"), index=True)
    student_id = db.Column(db.Integer,   db.ForeignKey("users.id"),      index=True)
    joined_at  = db.Column(db.DateTime,  default=datetime.datetime.utcnow)
    status     = db.Column(db.String(16), default="enrolled")

class ExamSession(db.Model):
    __tablename__ = "exam_sessions"
    id               = db.Column(db.String(36), primary_key=True)
    room_id          = db.Column(db.String(16), db.ForeignKey("exam_rooms.id"),  nullable=True, index=True)
    student_id       = db.Column(db.Integer,   db.ForeignKey("users.id"),        nullable=True, index=True)
    started_at       = db.Column(db.DateTime,  default=datetime.datetime.utcnow)
    ended_at         = db.Column(db.DateTime,  nullable=True)
    final_risk       = db.Column(db.String(16), default="Low")
    final_score      = db.Column(db.Float,     default=0.0)
    final_label      = db.Column(db.String(16), default="Focused")
    total_events     = db.Column(db.Integer,   default=0)
    frames_processed = db.Column(db.Integer,   default=0)
    # Full session webcam recording (Enhancement: full exam video recording).
    # Relative path under static/, e.g. "recordings/sess_<id>.webm".
    video_path       = db.Column(db.String(512), nullable=True)
    # Wall-clock instant the browser actually began recording, so each evidence
    # event's offset into the video = event.timestamp - video_started_at.
    video_started_at = db.Column(db.DateTime, nullable=True)
    # Phase 4: Behavioral State observations (JSON text, modules/behavior).  SEPARATE from
    # final_risk / final_score / events: never a violation, never part of the cheating risk.
    behavior_summary = db.Column(db.Text, nullable=True)
    events    = db.relationship("BehaviorEvent", backref="session", lazy="dynamic")
    snapshots = db.relationship("RiskSnapshot",  backref="session", lazy="dynamic")
    def to_dict(self):
        return {"id": self.id, "room_id": self.room_id, "student_id": self.student_id,
                "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "ended_at": self.ended_at.strftime("%Y-%m-%d %H:%M:%S") if self.ended_at else None,
                "final_risk": self.final_risk, "final_score": round(self.final_score, 3),
                "final_label": self.final_label, "total_events": self.total_events,
                "frames_processed": self.frames_processed,
                "video_path": self.video_path,
                "video_started_at": self.video_started_at.isoformat() if self.video_started_at else None}

class BehaviorEvent(db.Model):
    __tablename__ = "behavior_events"
    id              = db.Column(db.Integer, primary_key=True)
    session_id      = db.Column(db.String(36), db.ForeignKey("exam_sessions.id"), index=True)
    student_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    room_id         = db.Column(db.String(16), nullable=True, index=True)
    timestamp       = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    event_type      = db.Column(db.String(64),  nullable=False)
    severity        = db.Column(db.String(16),  default="Low")
    confidence      = db.Column(db.Float,       default=0.0)
    description     = db.Column(db.String(256), nullable=False)
    screenshot_path = db.Column(db.String(512), nullable=True)
    # Phase 7 (normalized event schema): detector/backend that produced the
    # event, how many detections were coalesced into it, and the per-session
    # sequence number (matches the live event log the student/proctor see).
    source          = db.Column(db.String(64),  nullable=True)
    repeat_count    = db.Column(db.Integer,     default=1)
    seq             = db.Column(db.Integer,     nullable=True)
    # Cumulative-risk points this event row actually added (0.0 for a row that
    # only continues an already-counted episode, e.g. a phone still in view after
    # the 12 s cooldown).  Lets a resumed/finalised session rebuild EXACTLY the
    # live cumulative risk.  NULL on rows written by older versions -> the
    # EPISODE weight of the event type is used for them (previous behaviour).
    cumulative_points = db.Column(db.Float, nullable=True)
    student = db.relationship("User", foreign_keys=[student_id])
    def to_dict(self):
        sname = self.student.username if self.student else "–"
        return {"id": self.id, "session_id": self.session_id,
                "source": self.source, "repeat_count": self.repeat_count or 1,
                "seq": self.seq,
                "timestamp_iso": self.timestamp.strftime("%Y-%m-%dT%H:%M:%S") + "Z" if self.timestamp else None,
                "student_id": self.student_id, "student_name": sname,
                "room_id": self.room_id,
                "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "event_type": self.event_type, "severity": self.severity,
                "confidence": round(self.confidence, 3), "description": self.description,
                "screenshot_path": self.screenshot_path,
                "cumulative_points": self.cumulative_points}

class RiskSnapshot(db.Model):
    __tablename__ = "risk_snapshots"
    id             = db.Column(db.Integer, primary_key=True)
    session_id     = db.Column(db.String(36), db.ForeignKey("exam_sessions.id"), index=True)
    student_id     = db.Column(db.Integer, nullable=True, index=True)
    room_id        = db.Column(db.String(16), nullable=True)
    timestamp      = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    risk_score     = db.Column(db.Float, default=0.0)
    risk_level     = db.Column(db.String(16), default="Low")
    behavior_label = db.Column(db.String(16), default="Focused")
    def to_dict(self):
        return {"timestamp": self.timestamp.strftime("%H:%M:%S"),
                "risk_score": round(self.risk_score, 3),
                "risk_level": self.risk_level, "behavior_label": self.behavior_label}


class QuestionEvent(db.Model):
    """
    Per-question telemetry — supports PDF §3 / §6.1 (Instructor Analytics
    Report correlates stress-related behaviour and response times with
    specific exam questions).

    The browser POSTs one row each time the student:
      • 'enter'  lands on / scrolls into the question
      • 'leave'  navigates to another question
      • 'answer' selects an option (one row per change)
      • 'submit' submits the exam (one synthetic row per active question)

    Each row carries the student's *current* risk snapshot at the moment of
    the event, so per-question correlation can be computed without joining
    against the RiskSnapshot table when desired.
    """
    __tablename__ = "question_events"
    id              = db.Column(db.Integer, primary_key=True)
    session_id      = db.Column(db.String(36), db.ForeignKey("exam_sessions.id"), index=True)
    student_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    room_id         = db.Column(db.String(16), nullable=True, index=True)
    question_id     = db.Column(db.String(32), nullable=False)   # e.g. "q1"
    question_index  = db.Column(db.Integer, default=0)           # 0-based ordinal
    question_text   = db.Column(db.String(512), default="")
    action          = db.Column(db.String(16), nullable=False)   # enter|leave|answer|submit
    answer_value    = db.Column(db.String(128), default="")
    timestamp       = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    # Snapshot of the student's risk state at the moment of this event
    risk_score      = db.Column(db.Float, default=0.0)
    risk_level      = db.Column(db.String(16), default="Low")
    behavior_label  = db.Column(db.String(16), default="Focused")

    def to_dict(self):
        return {"id": self.id, "session_id": self.session_id,
                "question_id": self.question_id,
                "question_index": self.question_index,
                "question_text": self.question_text,
                "action": self.action, "answer_value": self.answer_value,
                "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "risk_score": round(self.risk_score, 3),
                "risk_level": self.risk_level,
                "behavior_label": self.behavior_label}


class ExamQuestion(db.Model):
    """
    A single question belonging to an exam room.

    Question type is one of:
        mcq          — multiple choice, one correct answer
        true_false   — boolean
        short_answer — free-text response

    For mcq / true_false: ``options`` is JSON-encoded list of [value, label].
    For short_answer:     ``options`` is the empty string.

    ``correct_answer`` stores the canonical correct value (e.g. "b", "true").
    For short_answer questions, ``correct_answer`` is a lower-cased expected
    keyword the grader matches against (loose match — exact grading is out
    of scope for the proctoring deliverable).
    """
    __tablename__ = "exam_questions"
    id              = db.Column(db.Integer, primary_key=True)
    room_id         = db.Column(db.String(16), db.ForeignKey("exam_rooms.id"),
                                 nullable=False, index=True)
    order_index     = db.Column(db.Integer, default=0)
    qtype           = db.Column(db.String(16), default="mcq")
    text            = db.Column(db.String(1000), nullable=False)
    options_json    = db.Column(db.Text, default="[]")   # JSON of [[val,label],…]
    correct_answer  = db.Column(db.String(128), default="")
    marks           = db.Column(db.Float, default=1.0)
    image_url       = db.Column(db.String(256), default="")
    created_at      = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    room            = db.relationship("ExamRoom",
                                       backref=db.backref("questions",
                                                            lazy="dynamic",
                                                            cascade="all, delete-orphan",
                                                            order_by="ExamQuestion.order_index"))
    def options(self) -> list:
        import json
        try: return json.loads(self.options_json or "[]")
        except (ValueError, TypeError): return []
    def set_options(self, opts: list):
        import json
        self.options_json = json.dumps(opts, ensure_ascii=False)
    def to_dict(self, include_answer: bool = False) -> dict:
        out = {"id": self.id, "room_id": self.room_id,
                "order_index": self.order_index,
                "qtype": self.qtype, "text": self.text,
                "options": self.options(), "marks": self.marks,
                "image_url": self.image_url}
        if include_answer:
            out["correct_answer"] = self.correct_answer
        return out




# ── Lightweight forward-only schema upgrade ─────────────────────────────────
# db.create_all() never alters an existing table, so databases created by an
# older version of the project would lack the Phase 7 columns.  This adds any
# missing nullable column with ALTER TABLE ... ADD COLUMN (portable across
# SQLite/PostgreSQL/MySQL) and never drops or rewrites data.
_PHASE7_COLUMNS = {
    "behavior_events": [("source", "VARCHAR(64)"),
                        ("repeat_count", "INTEGER DEFAULT 1"),
                        ("seq", "INTEGER"),
                        ("cumulative_points", "FLOAT")],
    "exam_sessions": [("behavior_summary", "TEXT")],
}


def merge_behavior_summary(existing: str | None, segment: dict) -> str:
    """exam_sessions.behavior_summary = {"segments": [...]}; a resumed session gets one
    segment per live worker.  The segment with the same id is replaced (periodic saves)."""
    import json
    try:
        data = json.loads(existing) if existing else {}
        if not isinstance(data, dict):
            data = {}
    except (TypeError, ValueError):
        data = {}
    segs = [x for x in data.get("segments", []) if isinstance(x, dict)
            and x.get("segment") != segment.get("segment")]
    segs.append(segment)
    from core.json_safe import to_json_safe
    return json.dumps(to_json_safe({"segments": segs[-20:]}))


def parse_behavior_summary(text: str | None) -> dict | None:
    import json
    try:
        data = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("segments") else None


def _normalize_evidence_paths():
    """Older Windows runs stored evidence paths as `violations\\file.jpg`; the evidence route
    and every URL use `violations/file.jpg`.  Rewrite them once (idempotent, data-preserving)."""
    rows = (BehaviorEvent.query
            .filter(BehaviorEvent.screenshot_path.like("%\\%", escape="!")).all())
    for r in rows:
        r.screenshot_path = r.screenshot_path.replace("\\", "/")
    if rows:
        db.session.commit()
    return len(rows)


def ensure_schema():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    for table, cols in _PHASE7_COLUMNS.items():
        if table not in insp.get_table_names():
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                with db.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    _normalize_evidence_paths()
