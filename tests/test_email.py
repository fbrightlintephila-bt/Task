from datetime import datetime, timezone
from email_service import send_notification
from extensions import db
from models import Assignment, EmailLog, Evaluation, Submission


def test_email_disabled_is_logged_not_claimed_sent(app, users, monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    with app.app_context():
        assignment = Assignment(public_id="mail-token", title="Task", subject="General", description="Task", rubric_json={"A": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(user_id=users["student"], assignment_id=assignment.id, attempt_number=1, submission_text="work")
        db.session.add(submission)
        db.session.flush()
        evaluation = Evaluation(submission_id=submission.id, passing_score=90)
        db.session.add(evaluation)
        db.session.commit()
        log = send_notification(evaluation, "passed", "Subject", "Plain text", "<p>HTML</p>")
        assert log.delivery_status == "disabled"
        assert EmailLog.query.count() == 1


def test_unverified_address_is_blocked(app, users):
    with app.app_context():
        from models import User
        student = db.session.get(User, users["student"])
        student.email_verified = False
        assignment = Assignment(public_id="mail-token-2", title="Task", subject="General", description="Task", rubric_json={"A": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(user_id=users["student"], assignment_id=assignment.id, attempt_number=1, submission_text="work")
        db.session.add(submission)
        db.session.flush()
        evaluation = Evaluation(submission_id=submission.id, passing_score=90)
        db.session.add(evaluation)
        db.session.commit()
        log = send_notification(evaluation, "passed", "Subject", "Plain text", "<p>HTML</p>")
        assert log.delivery_status == "blocked"
