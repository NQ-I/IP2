"""app.py — Flask application factory for multi-student proctoring platform."""
import os, logging
from flask import Flask, redirect, url_for, render_template, jsonify
from flask_login import login_required, current_user
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from extensions import db, login_manager
from config import Config

# Phase 5 security fix: CSRF protection was previously entirely absent. This
# single CSRFProtect instance is shared across the app; it validates the
# X-CSRFToken header (or a csrf_token form field) on every state-changing
# request (POST/PUT/PATCH/DELETE) once initialised below. test_all.py's
# make_test_client() already sets app.config["WTF_CSRF_ENABLED"] = False
# for the test client, which is the standard Flask-WTF testing pattern
# (production behavior is unaffected — this only applies when the app is
# explicitly put in TESTING mode).
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    logging.basicConfig(
        level=getattr(logging, app.config.get("LOG_LEVEL","INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    csrf.init_app(app)

    @app.route("/api/csrf-token")
    @login_required
    def csrf_token_endpoint():
        """Lets an already-authenticated page fetch a fresh CSRF token for
        its own fetch()-based POST/PUT/PATCH/DELETE calls. The plain
        <form method="POST"> login page instead uses Flask-WTF's
        {{ csrf_token() }} Jinja helper directly (it doesn't need this
        endpoint since it isn't logged in yet)."""
        return jsonify({"csrf_token": generate_csrf()})

    # ── CRITICAL: import db_models so @login_manager.user_loader registers ──
    with app.app_context():
        import db_models  # noqa: F401 — registers user_loader

    from routes.auth        import auth_bp
    from routes.api         import api_bp
    from routes.api_student import student_bp
    from routes.api_proctor import proctor_bp
    from routes.api_admin   import admin_bp
    from routes.api_reports import reports_bp
    from routes.stream      import stream_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp,     url_prefix="/api")
    app.register_blueprint(student_bp)
    app.register_blueprint(proctor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(stream_bp)

    from core.session_manager import SessionManager
    app.session_manager = SessionManager(app)
    from core.audio_pipeline import AudioPipeline
    app.audio_pipeline = AudioPipeline(app.session_manager.get_worker)
    if app.config.get("AUDIO_WARMUP", True) and not app.config.get("TESTING"):
        import threading
        threading.Thread(target=app.audio_pipeline.warmup, daemon=True,
                         name="yamnet-warmup").start()

    os.makedirs(app.config["VIOLATIONS_DIR"], exist_ok=True)
    os.makedirs(app.config.get("RECORDINGS_DIR",
                os.path.join(app.config["BASE_DIR"], "static", "recordings")),
                exist_ok=True)
    os.makedirs(app.config["TRAINED_MODELS"], exist_ok=True)
    os.makedirs(os.path.join(app.config["BASE_DIR"], "instance"), exist_ok=True)
    # SQLite: many threads read (proctor polls) and write (event/snapshot writer, requests) at once.
    # WAL lets readers and the writer run concurrently and busy_timeout makes a writer wait instead of
    # failing with "database is locked".  (In-memory databases and other engines are left alone.)
    if str(app.config["SQLALCHEMY_DATABASE_URI"]).startswith("sqlite") and ":memory:" not in str(app.config["SQLALCHEMY_DATABASE_URI"]):
        from sqlalchemy import event
        with app.app_context():
            @event.listens_for(db.engine, "connect")
            def _sqlite_pragmas(dbapi_con, _rec):
                cur = dbapi_con.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA busy_timeout=15000")
                cur.close()

    with app.app_context():
        db.create_all()
        try:
            from db_models import ensure_schema
            ensure_schema()
        except Exception as exc:                      # noqa: BLE001
            app.logger.warning("schema upgrade skipped: %s", exc)

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self)")
        return resp

    @app.route("/favicon.ico")
    def favicon():
        # Browsers request it on every page load; the project has no icon (real log: 404s).
        return "", 204

    @app.route("/")
    @login_required
    def index():
        role = current_user.role
        if role == "admin":   return redirect(url_for("admin_dashboard"))
        if role == "proctor": return redirect(url_for("proctor_dashboard"))
        return redirect(url_for("student_exam"))

    @app.route("/proctor/dashboard")
    @login_required
    def proctor_dashboard():
        if current_user.role not in ("proctor", "admin"):
            return redirect(url_for("student_exam"))
        return render_template("proctor/dashboard.html", user=current_user)

    @app.route("/admin/dashboard")
    @login_required
    def admin_dashboard():
        if current_user.role != "admin":
            return redirect(url_for("proctor_dashboard"))
        return render_template("admin/dashboard.html", user=current_user)

    @app.route("/instructor/analytics")
    @login_required
    def instructor_analytics():
        # Instructor analytics is available to proctors and admins (the people
        # who review exams). Students are redirected away.
        if current_user.role not in ("proctor", "admin", "instructor"):
            return redirect(url_for("student_exam"))
        return render_template("instructor/analytics.html", user=current_user)

    # ── Authenticated evidence/recording serving ────────────────────────────
    # SECURITY FIX (Phase 2 audit): violation screenshots and full exam
    # recordings were stored under static/violations/ and static/recordings/,
    # which Flask's default static file handler serves to ANYONE with the
    # URL — no login, no ownership check. That means a student's webcam
    # evidence and full exam video (audio + video of their face) were
    # effectively public to anyone who obtained a link. These two routes are
    # registered with a more specific path than Flask's catch-all
    # `/static/<path:filename>` rule, so Werkzeug matches them first for
    # anything under static/violations/ or static/recordings/, while every
    # other static asset (CSS/JS) is unaffected and still served normally.
    def _room_owned_by_current_user(room_id) -> bool:
        if current_user.role == "admin":
            return True
        if not room_id:
            return False
        from db_models import ExamRoom
        room = ExamRoom.query.get(room_id)
        return bool(room and room.proctor_id == current_user.id)

    @app.route("/static/violations/<path:filename>")
    @login_required
    def violation_evidence(filename):
        from flask import abort, send_from_directory
        from db_models import BehaviorEvent
        rel = f"violations/{filename}"
        evt = BehaviorEvent.query.filter_by(screenshot_path=rel).first()
        if evt is None:
            abort(404)
        # Evidence images are for the proctor / admin / instructor review.  During the
        # exam a student used to be able to open the screenshots of his OWN violations,
        # which reveals what the proctoring AI flagged (requirement: no detection details
        # and no violation screenshots for the student during the exam).  After the
        # session ended the student keeps the previous access to his own evidence.
        own_ended = False
        if current_user.role == "student" and evt.student_id == current_user.id:
            from db_models import ExamSession
            sess = ExamSession.query.get(evt.session_id)
            own_ended = bool(sess and sess.ended_at is not None)
        allowed = (
            current_user.role == "admin"
            or own_ended
            or (current_user.role in ("proctor", "instructor")
                and _room_owned_by_current_user(evt.room_id))
        )
        if not allowed:
            abort(403)
        return send_from_directory(app.config["VIOLATIONS_DIR"], filename)

    @app.route("/static/recordings/<path:filename>")
    @login_required
    def session_recording(filename):
        from flask import abort, send_from_directory
        from db_models import ExamSession
        rel = f"recordings/{filename}"
        sess = ExamSession.query.filter_by(video_path=rel).first()
        if sess is None:
            abort(404)
        allowed = (
            current_user.role == "admin"
            or (current_user.role == "student" and sess.student_id == current_user.id)
            or (current_user.role in ("proctor", "instructor")
                and _room_owned_by_current_user(sess.room_id))
        )
        if not allowed:
            abort(403)
        recordings_dir = app.config.get(
            "RECORDINGS_DIR",
            os.path.join(app.config["BASE_DIR"], "static", "recordings"))
        return send_from_directory(recordings_dir, filename)

    # SECURITY FIX (phase-2 verification): Flask's built-in /static/<path:filename> handler
    # normalises the path itself, so "/static/./violations/<file>", "/static/%2e/violations/…",
    # "/static/css/../violations/…" and, on a case-insensitive disk (Windows),
    # "/static/Violations/…" never matched the two protected routes above and were served
    # to ANYONE (verified with raw HTTP on a real server: anonymous 200 with the JPEG, the
    # same for recordings).  Every static request that resolves inside the evidence or
    # recordings folder is now handed to the protected view (login + ownership checks).
    _plain_static = app.view_functions["static"]

    def _protected_target(filename):
        try:
            target = os.path.realpath(os.path.join(app.static_folder, filename))
        except (TypeError, ValueError):
            return None
        for folder, view in ((app.config["VIOLATIONS_DIR"], violation_evidence),
                             (app.config.get("RECORDINGS_DIR",
                                             os.path.join(app.config["BASE_DIR"], "static", "recordings")),
                              session_recording)):
            root = os.path.realpath(folder)
            nt, nr = os.path.normcase(target), os.path.normcase(root)
            if nt == nr or nt.startswith(nr + os.sep):
                return view, os.path.relpath(target, root).replace(os.sep, "/")
        return None

    def guarded_static(filename):
        hit = _protected_target(filename)
        if hit is not None:
            view, rel = hit
            return view(rel)
        return _plain_static(filename=filename)

    app.view_functions["static"] = guarded_static

    @app.route("/exam")
    @login_required
    def student_exam():
        # Only students take exams (admins: explicit test session).  A proctor
        # opening /exam used to be able to start a "student" session.
        if current_user.role == "proctor":
            return redirect(url_for("proctor_dashboard"))
        if current_user.role not in ("student", "admin"):
            return jsonify({"error": "Students only."}), 403
        return render_template("student/exam.html", user=current_user)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error."}), 500

    return app

if __name__ == "__main__":
    # `python app.py` used to start a second, different entry point (no HTTPS, no start-up checks).
    # There is exactly one supported launcher:
    from run import main
    main()
