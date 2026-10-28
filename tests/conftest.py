import pytest
from app import create_app
from extensions import db
from models import User


@pytest.fixture

def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SECRET_KEY": "test-secret",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture

def client(app):
    return app.test_client()


@pytest.fixture

def users(app):
    with app.app_context():
        student = User(full_name="Student One", student_id="S100", email="one@example.test", role="student", email_verified=True)
        student.set_password("student-password-long")
        teacher = User(full_name="Teacher One", email="teacher@example.test", role="teacher", email_verified=True)
        teacher.set_password("teacher-password-long")
        other = User(full_name="Student Two", student_id="S200", email="two@example.test", role="student", email_verified=True)
        other.set_password("student-password-long")
        db.session.add_all([student, teacher, other])
        db.session.commit()
        return {"student": student.id, "teacher": teacher.id, "other": other.id}
