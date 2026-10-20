"""
Root pytest configuration.

The legacy suites (test_all.py, test_smoke.py) build the application with the default Config, whose database is
instance/proctor.db - i.e. running the tests used to MODIFY the shipped database (rows were rewritten).  Point the default
database at a throw-away file BEFORE any test module imports config, so no test can touch real data.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="proctor_tests_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "tests.db").replace("\\", "/")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789abcdef")
