from extensions import db
from models import Assignment, ResubmissionSchedule, Submission
import app as app_module


def test_submission_saved_when_ai_is_unavailable(app, client, users, monkeypatch):
    with app.app_context():
        assignment = Assignment(public_id="workflow-token", title="Workflow task", subject="Python", description="Write a small function", requirements="Return a value", rubric_json={"Requirements": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.commit()
    client.post("/login", data={"email": "one@example.test", "password": "student-password-long"})
    monkeypatch.setattr(app_module, "evaluate_submission", lambda **kwargs: (_ for _ in ()).throw(app_module.AIServiceError("Unavailable")))
    response = client.post("/assignments/workflow-token", data={
        "submission_text": "def answer(): return 42", "actual_output": "42",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Evaluation unavailable" in response.data
    assert b"Score unavailable" in response.data
    with app.app_context():
        stored = Submission.query.one()
        assert stored.submission_text.startswith("def answer")
        assert stored.evaluation.overall_score is None
        assert stored.evaluation.task_status == "evaluation_failed"


def evaluation_report(score):
    return {
        "overall_score": score,
        "summary": "Compared with the teacher's assignment requirements.",
        "completed_requirements": [],
        "partially_completed_requirements": [],
        "missing_requirements": [],
        "mistakes": [],
        "output_comparison": {"comparison_verified": False, "explanation": "Code was not executed."},
        "criteria_scores": [],
        "strengths": [],
        "improvement_suggestions": [],
        "next_steps": [],
        "evaluation_status": "passed" if score >= 90 else "needs_improvement",
        "task_status": "completed" if score >= 90 else "resubmission_required",
        "resubmission_required": score < 90,
    }


def test_score_below_90_creates_pending_resubmission_schedule(app, client, users, monkeypatch):
    with app.app_context():
        assignment = Assignment(public_id="below-threshold", title="Workflow task", subject="Python", description="Write a small function", requirements="Return a value", rubric_json={"Requirements": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.commit()
    client.post("/login", data={"email": "one@example.test", "password": "student-password-long"})
    monkeypatch.setattr(app_module, "evaluate_submission", lambda **kwargs: evaluation_report(89))
    response = client.post("/assignments/below-threshold", data={"submission_text": "attempt work"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Schedule Pending" in response.data
    with app.app_context():
        stored = Submission.query.one()
        schedule = ResubmissionSchedule.query.one()
        assert stored.evaluation.overall_score == 89
        assert stored.evaluation.resubmission_required is True
        assert schedule.status == "pending"
        assert schedule.opens_at is None
        assert schedule.deadline_at is None


def test_score_of_90_passes_without_resubmission_schedule(app, client, users, monkeypatch):
    with app.app_context():
        assignment = Assignment(public_id="exactly-90", title="Workflow task", subject="Python", description="Write a small function", requirements="Return a value", rubric_json={"Requirements": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.commit()
    client.post("/login", data={"email": "one@example.test", "password": "student-password-long"})
    monkeypatch.setattr(app_module, "evaluate_submission", lambda **kwargs: evaluation_report(90))
    response = client.post("/assignments/exactly-90", data={"submission_text": "passing work"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Passed" in response.data
    with app.app_context():
        stored = Submission.query.one()
        assert stored.evaluation.overall_score == 90
        assert stored.evaluation.resubmission_required is False
        assert ResubmissionSchedule.query.count() == 0


def test_student_can_upload_task_and_work_for_teacher_review(app, client, users, monkeypatch):
    monkeypatch.setattr(app_module, "evaluate_submission", lambda **kwargs: (_ for _ in ()).throw(app_module.AIServiceError("Not configured")))
    client.post("/login", data={"email": "one@example.test", "password": "student-password-long"})
    dashboard = client.get("/dashboard")
    assert b"Upload task and work" in dashboard.data
    response = client.post("/student/task-upload", data={
        "teacher_id": str(users["teacher"]),
        "title": "Student supplied assignment",
        "subject": "Python",
        "passing_score": "90",
        "task_description": "Write a function that adds two numbers.",
        "requirements": "Return the correct sum.",
        "expected_output": "add(2, 3) returns 5",
        "submission_text": "def add(a, b): return a + b",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Evaluation unavailable" in response.data
    with app.app_context():
        stored = Submission.query.one()
        assert stored.assignment.origin_student_id == users["student"]
        assert stored.assignment.created_by == users["teacher"]
        assert "adds two numbers" in stored.assignment.description
        assert "def add" in stored.submission_text
        assert stored.evaluation.overall_score is None
