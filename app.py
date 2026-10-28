import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from html import escape
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_
from flask_login import current_user, login_required
from dotenv import load_dotenv
from config import Config
from extensions import csrf, db, login_manager, migrate
from models import Assignment, Evaluation, ResubmissionSchedule, Submission, User
from evaluator import DEFAULT_RUBRIC, validate_rubric
from ai_service import AIServiceError, evaluate_submission
from submission_utils import UploadError, extract_submission
from email_service import send_notification
from auth import bp as auth_bp, limiter as auth_limiter

load_dotenv()


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise RuntimeError("FLASK_SECRET_KEY must be configured in the environment.")
        app.config["SECRET_KEY"] = secrets.token_urlsafe(48)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    auth_limiter.init_app(app)
    app.register_blueprint(auth_bp)

    @app.template_filter("schedule_time")
    def format_schedule_time(value, timezone_name):
        if value is None:
            return "Not confirmed"
        try:
            return as_utc(value).astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M %Z")
        except ZoneInfoNotFoundError:
            return as_utc(value).strftime("%Y-%m-%d %H:%M UTC")

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database tables created.")

    @app.cli.command("create-teacher")
    def create_teacher():
        import click
        email = click.prompt("Teacher email").strip().lower()
        name = click.prompt("Teacher name").strip()
        password = click.prompt("Teacher password", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Teacher passwords must be at least 12 characters.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("That email is already registered.")
        user = User(email=email, full_name=name, role="teacher", email_verified=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("Teacher account created.")

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.role == "teacher":
            assignments = Assignment.query.filter_by(created_by=current_user.id).order_by(Assignment.created_at.desc()).all()
            schedules = ResubmissionSchedule.query.join(Assignment).filter(Assignment.created_by == current_user.id).order_by(ResubmissionSchedule.status, ResubmissionSchedule.deadline_at).all()
            assignment_ids = [assignment.id for assignment in assignments]
            teacher_submissions = Submission.query.filter(Submission.assignment_id.in_(assignment_ids)).order_by(Submission.submitted_at.desc()).limit(50).all() if assignment_ids else []
            return render_template("teacher_dashboard.html", assignments=assignments, schedules=schedules, teacher_submissions=teacher_submissions)
        assignments = Assignment.query.filter(
            Assignment.active.is_(True),
            or_(Assignment.origin_student_id.is_(None), Assignment.origin_student_id == current_user.id),
        ).order_by(Assignment.created_at.desc()).all()
        submissions = Submission.query.filter_by(user_id=current_user.id).order_by(Submission.submitted_at.desc()).all()
        schedules = ResubmissionSchedule.query.filter_by(student_id=current_user.id).filter(
            ResubmissionSchedule.status.in_(["pending", "active"])
        ).order_by(ResubmissionSchedule.created_at.desc()).all()
        latest = {}
        for item in submissions:
            latest[item.assignment_id] = item
        teachers = User.query.filter_by(role="teacher", email_verified=True).order_by(User.full_name).all()
        return render_template("student_dashboard.html", assignments=assignments, submissions=list(latest.values()), total=len(submissions), schedules=schedules, teachers=teachers)

    @app.route("/teacher/assignments/new", methods=["GET", "POST"])
    @role_required("teacher")
    def create_assignment():
        if request.method == "POST":
            try:
                rubric_raw = request.form.get("rubric_json", "").strip()
                import json
                rubric = validate_rubric(json.loads(rubric_raw)) if rubric_raw else DEFAULT_RUBRIC
                passing = int(request.form.get("passing_score", "90"))
                if not 0 <= passing <= 100:
                    raise ValueError("Passing score must be between 0 and 100.")
            except Exception as exc:
                flash(f"Check the rubric and passing score: {exc}", "danger")
                return render_template("create_assignment.html", default_rubric=DEFAULT_RUBRIC)
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            if not title or not description:
                flash("Title and task description are required.", "danger")
            else:
                assignment = Assignment(
                    public_id=secrets.token_urlsafe(12), title=title,
                    subject=request.form.get("subject", "General").strip() or "General",
                    description=description,
                    requirements=request.form.get("requirements", "").strip(),
                    instructions=request.form.get("instructions", "").strip(),
                    expected_output=request.form.get("expected_output", "").strip() or None,
                    reference_solution=request.form.get("reference_solution", "").strip() or None,
                    test_cases=request.form.get("test_cases", "").strip() or None,
                    rubric_json=rubric, passing_score=passing, created_by=current_user.id,
                )
                db.session.add(assignment)
                db.session.commit()
                flash("Assignment created.", "success")
                return redirect(url_for("dashboard"))
        return render_template("create_assignment.html", default_rubric=DEFAULT_RUBRIC)

    @app.route("/assignments/<public_id>", methods=["GET", "POST"])
    @role_required("student")
    def submit_assignment(public_id):
        assignment = Assignment.query.filter_by(public_id=public_id, active=True).first_or_404()
        if request.method == "POST":
            try:
                text, file_path, filename = extract_submission(
                    request.files.get("file"), app.config["UPLOAD_FOLDER"], app.config["MAX_CONTENT_LENGTH"]
                )
            except UploadError as exc:
                flash(str(exc), "danger")
                return render_template("submit_assignment.html", assignment=assignment)
            pasted = request.form.get("submission_text", "").strip()
            content = "\n\n".join(part for part in (pasted, text) if part)
            if not content:
                flash("Upload a supported file or paste your work before submitting.", "danger")
                return render_template("submit_assignment.html", assignment=assignment)
            attempt = (db.session.query(db.func.max(Submission.attempt_number)).filter_by(
                user_id=current_user.id, assignment_id=assignment.id).scalar() or 0) + 1
            submission = Submission(user_id=current_user.id, assignment_id=assignment.id,
                                    attempt_number=attempt, submission_text=content,
                                    actual_output=request.form.get("actual_output", "").strip() or None,
                                    private_file_path=file_path, original_filename=filename)
            db.session.add(submission)
            db.session.flush()
            evaluation = Evaluation(submission=submission, passing_score=assignment.passing_score,
                                   evaluation_status="pending", task_status="evaluation_pending")
            db.session.add(evaluation)
            db.session.commit()
            previous = None
            if attempt > 1:
                prior = Submission.query.filter_by(user_id=current_user.id, assignment_id=assignment.id,
                                                   attempt_number=attempt - 1).first()
                previous = prior.evaluation.feedback_json if prior and prior.evaluation else None
            try:
                report = evaluate_submission(assignment=assignment, submission=submission, previous_attempt=previous)
                evaluation.overall_score = report["overall_score"]
                evaluation.evaluation_status = report["evaluation_status"]
                evaluation.task_status = report["task_status"]
                evaluation.resubmission_required = report["resubmission_required"]
                evaluation.feedback_json = report
                submission.status = "evaluated"
                if evaluation.resubmission_required:
                    ensure_pending_schedule(submission)
                db.session.commit()
                send_evaluation_email(evaluation, report)
                flash("Evaluation completed.", "success")
            except AIServiceError as exc:
                evaluation.evaluation_status = "failed"
                evaluation.task_status = "evaluation_failed"
                submission.status = "evaluation_failed"
                db.session.commit()
                flash(str(exc), "warning")
            return redirect(url_for("evaluation_report", submission_id=submission.id))
        return render_template("submit_assignment.html", assignment=assignment)

    @app.route("/student/task-upload", methods=["GET", "POST"])
    @role_required("student")
    def upload_task_for_evaluation():
        teachers = User.query.filter_by(role="teacher", email_verified=True).order_by(User.full_name).all()
        if request.method == "POST":
            teacher = db.session.get(User, request.form.get("teacher_id", type=int))
            if not teacher or teacher.role != "teacher" or not teacher.email_verified:
                flash("Choose an available teacher to review this task.", "danger")
                return render_template("student_task_upload.html", teachers=teachers)
            task_text = request.form.get("task_description", "").strip()
            task_file_path = None
            try:
                task_file_text, task_file_path, _ = extract_submission(
                    request.files.get("task_file"), app.config["UPLOAD_FOLDER"], app.config["MAX_CONTENT_LENGTH"]
                )
                work_text, work_path, work_filename = extract_submission(
                    request.files.get("work_file"), app.config["UPLOAD_FOLDER"], app.config["MAX_CONTENT_LENGTH"]
                )
            except UploadError as exc:
                if task_file_path:
                    Path(task_file_path).unlink(missing_ok=True)
                flash(str(exc), "danger")
                return render_template("student_task_upload.html", teachers=teachers)
            finally:
                if task_file_path:
                    Path(task_file_path).unlink(missing_ok=True)
            task_description = "\n\n".join(part for part in (task_text, task_file_text) if part)
            student_work = "\n\n".join(part for part in (request.form.get("submission_text", "").strip(), work_text) if part)
            title = request.form.get("title", "").strip()
            if not title or not task_description or not student_work:
                flash("Enter a title, provide the original task, and upload or paste your completed work.", "danger")
                return render_template("student_task_upload.html", teachers=teachers)
            try:
                passing_score = int(request.form.get("passing_score", "90"))
            except ValueError:
                passing_score = -1
            if not 0 <= passing_score <= 100:
                flash("Passing score must be between 0 and 100.", "danger")
                return render_template("student_task_upload.html", teachers=teachers)

            assignment = Assignment(
                public_id=secrets.token_urlsafe(12), title=title,
                subject=request.form.get("subject", "General").strip() or "General",
                description=task_description,
                requirements=request.form.get("requirements", "").strip(),
                instructions="Student-provided task; awaiting teacher review.",
                expected_output=request.form.get("expected_output", "").strip() or None,
                reference_solution=request.form.get("reference_solution", "").strip() or None,
                rubric_json=DEFAULT_RUBRIC, passing_score=passing_score,
                created_by=teacher.id, origin_student_id=current_user.id,
            )
            db.session.add(assignment)
            db.session.flush()
            submission = Submission(
                user_id=current_user.id, assignment_id=assignment.id, attempt_number=1,
                submission_text=student_work,
                actual_output=request.form.get("actual_output", "").strip() or None,
                private_file_path=work_path, original_filename=work_filename,
            )
            db.session.add(submission)
            db.session.flush()
            evaluation = Evaluation(submission=submission, passing_score=passing_score)
            db.session.add(evaluation)
            db.session.commit()
            try:
                report = evaluate_submission(assignment=assignment, submission=submission)
                evaluation.overall_score = report["overall_score"]
                evaluation.evaluation_status = report["evaluation_status"]
                evaluation.task_status = report["task_status"]
                evaluation.resubmission_required = report["resubmission_required"]
                evaluation.feedback_json = report
                submission.status = "evaluated"
                if evaluation.resubmission_required:
                    ensure_pending_schedule(submission)
                db.session.commit()
                send_evaluation_email(evaluation, report)
            except AIServiceError as exc:
                evaluation.evaluation_status = "failed"
                evaluation.task_status = "evaluation_failed"
                submission.status = "evaluation_failed"
                db.session.commit()
                flash(str(exc), "warning")
            return redirect(url_for("evaluation_report", submission_id=submission.id))
        return render_template("student_task_upload.html", teachers=teachers)

    @app.route("/reports/<int:submission_id>")
    @login_required
    def evaluation_report(submission_id):
        submission = db.session.get(Submission, submission_id) or abort(404)
        if current_user.role != "teacher" and submission.user_id != current_user.id:
            abort(404)
        if current_user.role == "teacher" and submission.assignment.created_by != current_user.id:
            abort(404)
        schedules = ResubmissionSchedule.query.filter_by(
            submission_id=submission.id
        ).filter(ResubmissionSchedule.status.in_(["pending", "active"])).order_by(
            ResubmissionSchedule.created_at.desc()
        ).all()
        return render_template("evaluation_report.html", submission=submission, schedules=schedules)

    @app.route("/teacher/schedules/<int:submission_id>", methods=["GET", "POST"])
    @role_required("teacher")
    def schedule_resubmission(submission_id):
        submission = db.session.get(Submission, submission_id) or abort(404)
        if submission.assignment.created_by != current_user.id or not submission.evaluation or not submission.evaluation.resubmission_required:
            abort(404)
        if request.method == "POST":
            try:
                timezone_name = request.form.get("timezone", "Asia/Kolkata")
                zone = ZoneInfo(timezone_name)
                opens = datetime.fromisoformat(request.form["opens_at"]).replace(tzinfo=zone).astimezone(timezone.utc)
                deadline = datetime.fromisoformat(request.form["deadline_at"]).replace(tzinfo=zone).astimezone(timezone.utc)
                if opens <= datetime.now(timezone.utc) or deadline <= opens:
                    raise ValueError
            except (KeyError, ValueError, ZoneInfoNotFoundError):
                flash("Choose a valid time zone, a future opening time, and a later deadline.", "danger")
                return render_template("resubmission_schedule.html", submission=submission)
            schedule = ResubmissionSchedule.query.filter_by(submission_id=submission.id, status="pending").first()
            if schedule is None:
                schedule = ResubmissionSchedule(
                    secure_identifier=secrets.token_urlsafe(32), student_id=submission.user_id,
                    assignment_id=submission.assignment_id, submission_id=submission.id,
                    created_by=current_user.id,
                )
                db.session.add(schedule)
            schedule.opens_at = opens
            schedule.deadline_at = deadline
            schedule.timezone = timezone_name
            schedule.instructions = request.form.get("instructions", "").strip()
            schedule.status = "active"
            db.session.commit()
            send_schedule_email(schedule)
            flash("Schedule saved.", "success")
            return redirect(url_for("dashboard"))
        return render_template("resubmission_schedule.html", submission=submission)

    @app.route("/teacher/students/<int:student_id>/verify-email", methods=["POST"])
    @role_required("teacher")
    def verify_student_email(student_id):
        student = db.session.get(User, student_id) or abort(404)
        submitted_to_teacher = Submission.query.join(Assignment).filter(
            Submission.user_id == student.id, Assignment.created_by == current_user.id
        ).first()
        if student.role != "student" or submitted_to_teacher is None:
            abort(404)
        student.email_verified = True
        db.session.commit()
        flash("Student email marked as verified after teacher confirmation.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/resubmissions/<secure_identifier>", methods=["GET", "POST"])
    @role_required("student", "teacher")
    def resubmission_upload(secure_identifier):
        schedule = ResubmissionSchedule.query.filter_by(secure_identifier=secure_identifier, status="active").first_or_404()
        if current_user.role == "student" and schedule.student_id != current_user.id:
            abort(404)
        if current_user.role == "teacher" and schedule.assignment.created_by != current_user.id:
            abort(404)
        now = datetime.now(timezone.utc)
        if now < as_utc(schedule.opens_at) or now > as_utc(schedule.deadline_at):
            abort(403)
        if request.method == "POST":
            try:
                text, path, filename = extract_submission(request.files.get("file"), app.config["UPLOAD_FOLDER"], app.config["MAX_CONTENT_LENGTH"])
            except UploadError as exc:
                flash(str(exc), "danger")
                return render_template("resubmission_upload.html", schedule=schedule)
            content = "\n\n".join(part for part in (request.form.get("submission_text", "").strip(), text) if part)
            if not content:
                flash("Upload a file or paste your corrected work.", "danger")
                return render_template("resubmission_upload.html", schedule=schedule)
            attempt = (db.session.query(db.func.max(Submission.attempt_number)).filter_by(
                user_id=schedule.student_id, assignment_id=schedule.assignment_id).scalar() or 0) + 1
            submission = Submission(user_id=schedule.student_id, assignment_id=schedule.assignment_id,
                                    attempt_number=attempt, submission_text=content,
                                    actual_output=request.form.get("actual_output", "").strip() or None,
                                    private_file_path=path, original_filename=filename)
            db.session.add(submission)
            db.session.flush()
            evaluation = Evaluation(submission=submission, passing_score=schedule.assignment.passing_score)
            db.session.add(evaluation)
            schedule.status = "used"
            db.session.commit()
            try:
                report = evaluate_submission(assignment=schedule.assignment, submission=submission,
                                            previous_attempt=schedule.submission.evaluation.feedback_json)
                evaluation.overall_score = report["overall_score"]
                evaluation.evaluation_status = report["evaluation_status"]
                evaluation.task_status = report["task_status"]
                evaluation.resubmission_required = report["resubmission_required"]
                evaluation.feedback_json = report
                submission.status = "evaluated"
                if evaluation.resubmission_required:
                    ensure_pending_schedule(submission)
                db.session.commit()
                send_evaluation_email(evaluation, report)
                flash("Resubmission evaluated.", "success")
            except AIServiceError as exc:
                evaluation.evaluation_status = "failed"
                evaluation.task_status = "evaluation_failed"
                submission.status = "evaluation_failed"
                db.session.commit()
                flash(str(exc), "warning")
            return redirect(url_for("evaluation_report", submission_id=submission.id))
        return render_template("resubmission_upload.html", schedule=schedule)

    return app


def ensure_pending_schedule(submission):
    existing = ResubmissionSchedule.query.filter_by(submission_id=submission.id, status="pending").first()
    if existing is None:
        db.session.add(ResubmissionSchedule(
            secure_identifier=secrets.token_urlsafe(32),
            student_id=submission.user_id,
            assignment_id=submission.assignment_id,
            submission_id=submission.id,
            timezone=Config.DEFAULT_TIMEZONE,
            status="pending",
            created_by=submission.assignment.created_by,
        ))


def send_evaluation_email(evaluation, report):
    user = evaluation.submission.user
    title = evaluation.submission.assignment.title
    score = report["overall_score"]
    passed = evaluation.evaluation_status == "passed"
    email_type = "passed" if passed else "resubmission_required"
    subject = "StudentEval AI — Task Completed Successfully" if passed else "StudentEval AI — Improvement and Resubmission Required"
    missing = "\n".join(f"- {item}" for item in report.get("missing_requirements", [])) or "None recorded."
    steps = "\n".join(f"- {item}" for item in report.get("next_steps", [])) or "Review your feedback report."
    url = url_for("evaluation_report", submission_id=evaluation.submission_id, _external=True)
    schedule_status = "No schedule confirmed yet; your teacher will share the date and time." if not passed else "No resubmission required."
    text = (f"Hello {user.full_name},\n\nAssignment: {title}\nAttempt: {evaluation.submission.attempt_number}\n"
            f"Score: {score}/100 (passing score {evaluation.passing_score:g})\nStatus: {evaluation.task_status}\n\n"
            f"{report.get('summary', '')}\n\nMissing requirements:\n{missing}\n\nNext steps:\n{steps}\n\n"
            f"Schedule status: {schedule_status}\nReport: {url}")
    html = (f"<p>Hello {escape(user.full_name)},</p><p><strong>{escape(title)}</strong> · Attempt "
            f"{evaluation.submission.attempt_number}</p><p>Score: {score:g}/100; passing score: "
            f"{evaluation.passing_score:g}. Status: {escape(evaluation.task_status)}.</p>"
            f"<p>{escape(report.get('summary', ''))}</p><p>Missing requirements:<br>{escape(missing).replace(chr(10), '<br>')}</p>"
            f"<p>Next steps:<br>{escape(steps).replace(chr(10), '<br>')}</p>"
            f"<p>{escape(schedule_status)}</p><p><a href=\"{escape(url, quote=True)}\">Open evaluation report</a></p>")
    return send_notification(evaluation, email_type, subject, text, html)


def send_schedule_email(schedule):
    evaluation = schedule.submission.evaluation
    url = url_for("resubmission_upload", secure_identifier=schedule.secure_identifier, _external=True)
    title = schedule.assignment.title
    instructions = schedule.instructions or "Review your previous feedback and submit corrected work."
    zone = ZoneInfo(schedule.timezone)
    opens_local = as_utc(schedule.opens_at).astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
    deadline_local = as_utc(schedule.deadline_at).astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")
    text = (f"Your resubmission schedule for {title} is confirmed.\nOpening: {opens_local}\n"
            f"Deadline: {deadline_local}\nTime zone: {schedule.timezone}\nInstructions: {instructions}\n"
            f"Resubmission link: {url}")
    html = (f"<p>Your resubmission schedule for <strong>{escape(title)}</strong> is confirmed.</p>"
            f"<p>Opening: {escape(opens_local)}<br>Deadline: {escape(deadline_local)}<br>"
            f"Time zone: {escape(schedule.timezone)}</p><p>{escape(instructions)}</p>"
            f"<p><a href=\"{escape(url, quote=True)}\">Open resubmission page</a></p>")
    return send_notification(evaluation, "schedule_confirmed", "StudentEval AI — Your Resubmission Schedule", text, html)


app = create_app()
