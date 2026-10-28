from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    student_id = db.Column(db.String(80), unique=True, nullable=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(120), nullable=False, default="General")
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=False, default="")
    instructions = db.Column(db.Text, nullable=False, default="")
    expected_output = db.Column(db.Text)
    reference_solution = db.Column(db.Text)
    test_cases = db.Column(db.Text)
    rubric_json = db.Column(db.JSON, nullable=False)
    passing_score = db.Column(db.Integer, nullable=False, default=90)
    opening_at = db.Column(db.DateTime(timezone=True))
    initial_deadline_at = db.Column(db.DateTime(timezone=True))
    allowed_extensions = db.Column(db.String(200), nullable=False, default=".py,.txt,.pdf,.docx,.md")
    max_upload_bytes = db.Column(db.Integer, nullable=False, default=5 * 1024 * 1024)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    origin_student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    creator = db.relationship("User", foreign_keys=[created_by], backref="assignments")
    origin_student = db.relationship("User", foreign_keys=[origin_student_id])


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False, index=True)
    attempt_number = db.Column(db.Integer, nullable=False)
    private_file_path = db.Column(db.String(500))
    original_filename = db.Column(db.String(255))
    submission_text = db.Column(db.Text, nullable=False, default="")
    actual_output = db.Column(db.Text)
    status = db.Column(db.String(40), nullable=False, default="submitted")
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user = db.relationship("User", backref="submissions")
    assignment = db.relationship("Assignment", backref="submissions")
    __table_args__ = (db.UniqueConstraint("user_id", "assignment_id", "attempt_number"),)


class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False, unique=True)
    overall_score = db.Column(db.Float)
    maximum_score = db.Column(db.Float, nullable=False, default=100)
    passing_score = db.Column(db.Float, nullable=False)
    evaluation_status = db.Column(db.String(40), nullable=False, default="pending")
    task_status = db.Column(db.String(50), nullable=False, default="evaluation_pending")
    resubmission_required = db.Column(db.Boolean, nullable=False, default=False)
    feedback_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    submission = db.relationship("Submission", backref=db.backref("evaluation", uselist=False))


class ResubmissionSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    secure_identifier = db.Column(db.String(64), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False)
    opens_at = db.Column(db.DateTime(timezone=True))
    deadline_at = db.Column(db.DateTime(timezone=True))
    timezone = db.Column(db.String(80), nullable=False, default="Asia/Kolkata")
    instructions = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(30), nullable=False, default="active")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    student = db.relationship("User", foreign_keys=[student_id], backref="resubmission_schedules")
    creator = db.relationship("User", foreign_keys=[created_by])
    assignment = db.relationship("Assignment")
    submission = db.relationship("Submission")


class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluation.id"), nullable=False, index=True)
    recipient = db.Column(db.String(254), nullable=False)
    email_type = db.Column(db.String(50), nullable=False)
    delivery_status = db.Column(db.String(30), nullable=False, default="pending")
    attempts = db.Column(db.Integer, nullable=False, default=0)
    sent_at = db.Column(db.DateTime(timezone=True))
    error_summary = db.Column(db.String(500))
    idempotency_key = db.Column(db.String(160), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    evaluation = db.relationship("Evaluation", backref="email_logs")
