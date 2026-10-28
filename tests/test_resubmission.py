from datetime import datetime, timedelta, timezone
from extensions import db
from models import Assignment, Evaluation, ResubmissionSchedule, Submission


def login(client, email):
    client.post("/login", data={"email": email, "password": "student-password-long"})


def test_schedule_link_requires_ownership_and_valid_window(app, client, users):
    with app.app_context():
        assignment = Assignment(public_id="task-token", title="Task", subject="General", description="Task", rubric_json={"A": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(user_id=users["student"], assignment_id=assignment.id, attempt_number=1, submission_text="work")
        db.session.add(submission)
        db.session.flush()
        evaluation = Evaluation(submission_id=submission.id, passing_score=90, overall_score=80, evaluation_status="needs_improvement", task_status="resubmission_required", resubmission_required=True)
        db.session.add(evaluation)
        schedule = ResubmissionSchedule(secure_identifier="unguessable-example-token", student_id=users["student"], assignment_id=assignment.id, submission_id=submission.id, opens_at=datetime.now(timezone.utc)-timedelta(minutes=1), deadline_at=datetime.now(timezone.utc)+timedelta(hours=1), created_by=users["teacher"])
        db.session.add(schedule)
        db.session.commit()
    login(client, "two@example.test")
    assert client.get("/resubmissions/unguessable-example-token").status_code == 404
    client.post("/logout")
    login(client, "one@example.test")
    assert client.get("/resubmissions/unguessable-example-token").status_code == 200


def test_resubmission_before_open_is_rejected(app, client, users):
    with app.app_context():
        assignment = Assignment(public_id="task-token-2", title="Task", subject="General", description="Task", rubric_json={"A": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(user_id=users["student"], assignment_id=assignment.id, attempt_number=1, submission_text="work")
        db.session.add(submission)
        db.session.flush()
        schedule = ResubmissionSchedule(secure_identifier="future-token", student_id=users["student"], assignment_id=assignment.id, submission_id=submission.id, opens_at=datetime.now(timezone.utc)+timedelta(hours=1), deadline_at=datetime.now(timezone.utc)+timedelta(hours=2), created_by=users["teacher"])
        db.session.add(schedule)
        db.session.commit()
    login(client, "one@example.test")
    assert client.get("/resubmissions/future-token").status_code == 403
