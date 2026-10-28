from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import or_
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from extensions import db, login_manager
from models import User

bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=[])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        student_id = request.form.get("student_id", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not student_id or "@" not in email or len(password) < 10 or password != confirm:
            flash("Check your details. Passwords must match and be at least 10 characters.", "danger")
        elif User.query.filter(or_(User.email == email, User.student_id == student_id)).first():
            flash("Unable to create account with those details.", "danger")
        else:
            user = User(full_name=name, student_id=student_id, email=email, role="student")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. Email ownership verification is not configured in this local build; ask a teacher to confirm your account.", "warning")
            return redirect(url_for("auth.login"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=False, fresh=True)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Unable to sign in with those details.", "danger")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect(url_for("index"))
