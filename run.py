"""
run.py — Production entry point for the AI Exam Proctoring System.

Usage:
    python run.py              # default: port 5000
    python run.py --port 8080  # custom port
    python run.py --host 0.0.0.0 --port 5000

Performs startup validation:
  1. Checks trained model exists
  2. Initialises database tables
  3. Checks OpenCV is importable
  4. Starts Flask in threaded mode
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Windows consoles/pipes may use a legacy code page (cp1252); the banner and status lines contain
# box-drawing characters, so force UTF-8 (never crash on output when redirected to a file).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:            # not a text stream / very old Python
        pass

BANNER = """
╔══════════════════════════════════════════════════════════╗
║        AI ONLINE EXAM PROCTORING SYSTEM                  ║
║        King Faisal University — CS Graduation 2026       ║
║                                                          ║
║  Team:  Nasser Alqahtani  · Radi Alsadah  · Mazen Alshagawi
║  Supervisor: Dr. Raid Mohammad Alzubi                    ║
╚══════════════════════════════════════════════════════════╝
"""


def check_prerequisites():
    """Run before app creation to catch fatal issues early."""
    errors = []
    warnings = []

    # Python version
    if sys.version_info < (3, 10):
        errors.append("Python 3.10 or later is required.")

    # Core imports
    try: import flask
    except ImportError: errors.append("flask not installed. Run: pip install flask")

    try: import flask_sqlalchemy
    except ImportError: errors.append("flask-sqlalchemy not installed.")

    try: import flask_login
    except ImportError: errors.append("flask-login not installed.")

    try: import numpy
    except ImportError: errors.append("numpy not installed.")

    try: import cv2
    except ImportError: errors.append("opencv-python not installed.")

    try: import mediapipe
    except ImportError: warnings.append("mediapipe not installed — face analysis will be disabled.")

    try: import sklearn
    except ImportError: errors.append("scikit-learn not installed.")

    try: import ultralytics
    except ImportError: warnings.append("ultralytics not installed — phone detection will be disabled.")

    try: import matplotlib   # required by evaluate_model.py and reporting
    except ImportError: warnings.append("matplotlib not installed — PDF reports + benchmark charts disabled.")

    try: import reportlab    # required by reporting
    except ImportError: warnings.append("reportlab not installed — PDF report generation disabled. (pip install reportlab)")

    # ── Model files ─────────────────────────────────────────────────────────
    here  = os.path.dirname(__file__)

    rf_path = os.path.join(here, "trained_models", "rf_classifier.pkl")
    if not os.path.exists(rf_path):
        warnings.append(
            "trained_models/rf_classifier.pkl missing. "
            "Run:  python train_model.py  to train the Random Forest classifier. "
            "The system will use a fallback heuristic until then.")

    yolo_path = os.path.join(here, "models", "yolov8m.pt")
    if not os.path.exists(yolo_path):
        warnings.append(
            "models/yolov8m.pt missing. Phone detection will use the lightweight "
            "MediaPipe fallback (less accurate). "
            "Install once with:  python -c \"from ultralytics import YOLO; YOLO('yolov8m.pt')\" "
            "and move the file into models/.")
    else:
        size = os.path.getsize(yolo_path)
        if size < 10 * 1024 * 1024:
            warnings.append(
                f"models/yolov8m.pt is only {size/1024:.0f} KB — looks like a stub or "
                f"git-lfs pointer, not the real ~52 MB model. Phone detection will "
                f"fall back to MediaPipe. See README for how to install the real weights.")

    for fname in ("blaze_face_short_range.tflite", "face_landmarker.task"):
        fpath = os.path.join(here, "models", fname)
        if not os.path.exists(fpath):
            warnings.append(f"models/{fname} missing — face analysis will fail at startup.")

    return errors, warnings


def print_startup_info(host, port, https=False):
    from core.netinfo import lan_ips
    scheme = "https" if https else "http"
    ips = lan_ips() if host in ("0.0.0.0", "::") else [host]
    print(f"\n  Access URLs ({scheme.upper()}):")
    print(f"    This computer : {scheme}://localhost:{port}")
    for ip in ips:
        print(f"    Other devices : {scheme}://{ip}:{port}")
    main_ip = ips[0] if ips else "SERVER-IP"
    print(f"\n  Role URLs (replace localhost by the server IP on OTHER devices):")
    print(f"    Admin    → {scheme}://localhost:{port}/admin/dashboard")
    print(f"    Proctor  → {scheme}://localhost:{port}/proctor/dashboard")
    if https:
        print(f"    Student  → {scheme}://{main_ip}:{port}/exam")
    else:
        # Over plain http the browser allows the camera only at localhost / 127.0.0.1 (the
        # LAN address printed here before blocked it).  127.0.0.1 also keeps the student's
        # login separate from the proctor's localhost login in the same browser.
        print(f"    Student  → {scheme}://127.0.0.1:{port}/exam   (on THIS computer; separate login from localhost)")
    if not https and host in ("0.0.0.0", "::"):
        print("\n  ⚠  HTTP only: another laptop's browser will BLOCK the camera and microphone.")
        print("     Restart with:  python run.py --https      (see LAN_GUIDE.md)")
    if https:
        print("\n  On each student device the browser shows a certificate warning the first time:")
        print("     Advanced → Proceed to <ip> (unsafe).  This is expected for a self-signed test certificate.")
    print(f"\n  Windows firewall (run ONCE in an Administrator terminal):")
    print(f'     netsh advfirewall firewall add rule name="ExamProctor" dir=in action=allow protocol=TCP localport={port}')
    print(f"\n  Demo accounts (run with --setup first):")
    print(f"    admin    / admin123")
    print(f"    proctor1 / proctor123")
    print(f"    student1 … student5 / student123      (test passwords - change before real use)")
    print(f"\n  Press Ctrl+C to stop\n")
    print("─" * 60)


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(description="AI Exam Proctoring System")
    parser.add_argument("--host",  default="0.0.0.0",  help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port",  default=5000, type=int, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true",   help="Enable Flask debug mode")
    parser.add_argument("--setup", action="store_true",   help="Run setup_demo.py before starting")
    parser.add_argument("--https", action="store_true",
                        help="Serve over HTTPS with an auto-generated self-signed certificate "
                             "(REQUIRED for camera/microphone on other devices)")
    args = parser.parse_args()

    # The Werkzeug debugger allows remote code execution: never expose it to the network.
    if args.debug and args.host not in ("127.0.0.1", "localhost"):
        print("  ✗  --debug is refused when the server listens on the network "
              f"(--host {args.host}). Use --host 127.0.0.1 with --debug.")
        sys.exit(2)
    if args.https:
        os.environ["SESSION_COOKIE_SECURE"] = "1"      # cookies only over HTTPS (read by config.py)

    # Which copy of the project is running (a test once ran an OLD folder by mistake:
    # every path in its log was ...\exam_proctor_latest_2026-09-14\exam_proctor\...).
    print(f"  Project folder : {os.path.dirname(os.path.abspath(__file__))}")
    print(f"  Python         : {sys.executable}")
    print(f"  PROCTOR_DIAG   : {'ON' if os.environ.get('PROCTOR_DIAG') == '1' else 'off'}")
    print("[1/4] Checking prerequisites…")
    errors, warnings = check_prerequisites()
    for w in warnings: print(f"  ⚠  {w}")
    for e in errors:   print(f"  ✗  {e}")
    if errors:
        print("\n  Cannot start: fix the errors above first.")
        sys.exit(1)
    print("  ✓  All required packages present")

    # Optional: run demo setup
    if args.setup:
        print("\n[1b] Running demo setup…")
        import setup_demo
        setup_demo.run()

    print("\n[2/4] Creating Flask application…")
    from app import create_app
    from config import Config
    app = create_app(Config)
    print("  ✓  App created, DB tables initialised")

    print("\n[3/4] Loading AI models…")
    model_path = os.path.join(os.path.dirname(__file__), "trained_models", "rf_classifier.pkl")
    if os.path.exists(model_path):
        print("  ✓  rf_classifier.pkl found")
    else:
        print("  ⚠  rf_classifier.pkl missing — running without trained RF")

    print("\n[4/4] Starting server…")
    ssl_ctx = None
    if args.https:
        from core.netinfo import lan_ips
        from core.tls import ensure_self_signed_cert
        crt, key, addrs = ensure_self_signed_cert(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "certs"), lan_ips())
        ssl_ctx = (crt, key)
        print(f"  ✓  HTTPS certificate: {crt}  (valid for: {', '.join(addrs)})")
    print_startup_info(args.host, args.port, https=bool(ssl_ctx))

    # ONE process, many threads: workers, the SSE event bus and the detector
    # pool live in this process's memory.  Do not start several server processes.
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True,
        use_reloader=False,   # avoid double session-manager init
        ssl_context=ssl_ctx,
    )


if __name__ == "__main__":
    main()
