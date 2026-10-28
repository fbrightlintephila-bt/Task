import os
from pathlib import Path


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///student_eval_ai.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(Path("instance") / "uploads"))
    DEFAULT_PASSING_SCORE = int(os.getenv("DEFAULT_PASSING_SCORE", "90"))
    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
