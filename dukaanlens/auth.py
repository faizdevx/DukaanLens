"""Register, log in, log out."""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import func

from .extensions import db
from .models import User
from .validators import EMAIL_RE

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only allow redirects to paths on this site (prevents open redirects)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = []
        if not 3 <= len(username) <= 30 or not username.replace("_", "").replace(".", "").isalnum():
            errors.append("Username must be 3-30 characters: letters, numbers, _ or .")
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if len(password) > 128:
            errors.append("Password is too long.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not errors:
            if User.query.filter(func.lower(User.username) == username.lower()).first():
                errors.append("That username is already taken.")
            if User.query.filter_by(email=email).first():
                errors.append("That email is already registered.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("register.html", username=username, email=email), 400

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome to DukaanLens! Let's set up your shop.", "success")
        return redirect(url_for("main.setup"))
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            (func.lower(User.username) == identity.lower()) | (User.email == identity.lower())
        ).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        flash("Wrong username/email or password.", "danger")
        return render_template("login.html", identity=identity), 401
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
