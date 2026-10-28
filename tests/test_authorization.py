from extensions import db
from models import Assignment, Evaluation, Submission


def create_records(app, users):
    with app.app_context():
        assignment = Assignment(public_id="public-assignment-token", title="Task", subject="Math", description="Describe task", requirements="Solve", instructions="", rubric_json={"A": 100}, passing_score=90, created_by=users["teacher"])
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(user_id=users["student"], assignment_id=assignment.id, attempt_number=1, submission_text="answer")
        db.session.add(submission)
        db.session.flush()
        evaluation = Evaluation(submission_id=submission.id, passing_score=90, overall_score=50, evaluation_status="needs_improvement", task_status="resubmission_required", resubmission_required=True)
        db.session.add(evaluation)
        db.session.commit()
        return submission.id


def login(client, email):
    client.post("/login", data={"email": email, "password": "student-password-long"})


def test_student_cannot_view_another_students_report(app, client, users):
    submission_id = create_records(app, users)
    login(client, "two@example.test")
    assert client.get(f"/reports/{submission_id}").status_code == 404


def test_student_cannot_create_assignment(app, client, users):
    login(client, "one@example.test")
    assert client.get("/teacher/assignments/new").status_code == 403


def test_teacher_can_view_own_submission(app, client, users):
    submission_id = create_records(app, users)
    client.post("/login", data={"email": "teacher@example.test", "password": "teacher-password-long"})
    assert client.get(f"/reports/{submission_id}").status_code == 200
