"""
config.py — Production configuration for multi-student proctoring platform.
"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

_DEFAULT_SECRET_FALLBACK = "kfu-proctor-2026-change-in-prod"


class Config:
    _DEFAULT_SECRET = "kfu-proctor-2026-change-in-prod"

    @staticmethod
    def _load_or_create_secret():
        """Phase 7: never sign sessions with the public default.  Use the
        SECRET_KEY env var if set, otherwise a random key generated once and
        persisted (0600) in instance/secret_key."""
        env = os.environ.get("SECRET_KEY")
        if env:
            return env
        path = os.path.join(BASE_DIR, "instance", "secret_key")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    v = f.read().strip()
                if len(v) >= 32:
                    return v
            import secrets
            os.makedirs(os.path.dirname(path), exist_ok=True)
            v = secrets.token_hex(32)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(v)
            return v
        except OSError:
            return _DEFAULT_SECRET_FALLBACK

    SECRET_KEY = None  # set below
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 512))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    AI_ASYNC = os.environ.get("AI_ASYNC", "1") not in ("0", "false", "False")
    BASE_DIR   = BASE_DIR
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR,'instance','proctor.db')}"
    )
    # Heroku-style "postgres://" URLs are rejected by SQLAlchemy 2.x; accept them.
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = "postgresql://" + SQLALCHEMY_DATABASE_URI[len("postgres://"):]
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=10)

    # Storage
    VIOLATIONS_DIR  = os.path.join(BASE_DIR, "static", "violations")
    RECORDINGS_DIR  = os.path.join(BASE_DIR, "static", "recordings")

    # Phase 5 privacy fix: previously no retention/deletion policy existed
    # anywhere in the project — evidence (screenshots, full session
    # recordings with audio) was kept forever. RETENTION_DAYS is
    # deliberately opt-in/configurable rather than a background timer:
    # scripts/retention_cleanup.py only deletes evidence for sessions that
    # (a) have actually ended (ended_at IS NOT NULL — never touches an
    # active session) and (b) ended more than RETENTION_DAYS ago. Set to 0
    # to disable cleanup entirely (the default remains "keep everything"
    # unless an operator explicitly configures and runs the script).
    RETENTION_DAYS  = int(os.environ.get("RETENTION_DAYS", 0))
    MODELS_DIR      = os.path.join(BASE_DIR, "models")
    TRAINED_MODELS  = os.path.join(BASE_DIR, "trained_models")

    # Stream / detection
    CAMERA_INDEX        = int(os.environ.get("CAMERA_INDEX", 0))
    STREAM_FPS          = 25
    PHONE_THRESHOLD     = 0.25
    PHONE_CONFIRM_SECS  = 2.0
    AUDIO_ENABLED       = True

    # Risk thresholds
    RISK_LOW_MAX    = 0.35
    RISK_MEDIUM_MAX = 0.65

    # Multi-student settings
    MAX_CONCURRENT_STUDENTS = 30
    FRAME_PROCESS_INTERVAL  = 1.0   # seconds between frame processing per student
    SNAPSHOT_INTERVAL       = 5.0   # seconds between risk snapshots
    EVENT_COOLDOWN          = 8.0   # seconds before re-logging same event type
    PHONE_HOLD_SECS         = 1.2   # hold phone detection across frames

    # SSE heartbeat
    SSE_HEARTBEAT_SECS = 15

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


Config.SECRET_KEY = Config._load_or_create_secret()
if Config.SECRET_KEY == _DEFAULT_SECRET_FALLBACK:
    import warnings
    warnings.warn("SECRET_KEY could not be persisted; using the public default.", RuntimeWarning)
