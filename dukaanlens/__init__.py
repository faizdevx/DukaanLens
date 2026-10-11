"""DukaanLens: a small finance dashboard for shop owners."""
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, request, session

from .extensions import db, login_manager


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)

    # Secrets and settings come from environment variables (see .env.example).
    # With no SECRET_KEY we make a random one: fine for trying the app, but you
    # will be logged out on every restart, so set a real one in .env.
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(app.instance_path, "dukaanlens.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (registers the tables)
    from .auth import bp as auth_bp
    from .budgets import bp as budgets_bp
    from .chat import bp as chat_bp
    from .main import bp as main_bp
    from .records import bp as records_bp
    from .uploads import bp as uploads_bp

    for blueprint in (auth_bp, main_bp, records_bp, budgets_bp, uploads_bp, chat_bp):
        app.register_blueprint(blueprint)

    @app.errorhandler(413)
    def file_too_large(error):
        from flask import flash, redirect, url_for
        flash("That file is too large (maximum 5 MB).", "danger")
        return redirect(url_for("uploads.list_uploads"))

    # --- CSRF protection: every POST must carry the token stored in the session.
    @app.before_request
    def check_csrf():
        if request.method == "POST":
            expected = session.get("csrf_token")
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not expected or not sent or not secrets.compare_digest(expected, sent):
                abort(400, "Invalid or missing CSRF token. Go back, refresh and try again.")

    @app.context_processor
    def inject_helpers():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        from .finance import format_money
        from .models import TRANSACTION_TYPES, TYPE_LABELS
        return {
            "csrf_token": session["csrf_token"],
            "TRANSACTION_TYPES": TRANSACTION_TYPES,
            "TYPE_LABELS": TYPE_LABELS,
            "money": format_money,
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        db.create_all()
        print("Database ready.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Create a demo user with sample records."""
        from .seed import seed_demo
        print(seed_demo())

    with app.app_context():
        db.create_all()

    return app
