"""
extensions.py — Shared Flask extension singletons.
Import from here to avoid circular import issues.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
