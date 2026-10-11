"""Dashboard, first-login shop setup and settings."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import finance, queries
from .extensions import db
from .models import FinancialRecord, Shop
from .periods import ALL_TIME, month_period, period_from_key
from .utils import shop_required
from .validators import clean_text, collect_errors, parse_amount, parse_date

bp = Blueprint("main", __name__)

PERIOD_OPTIONS = [("all", "All time"), ("year", "This year"), ("month", "This month")]


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    if current_user.shop is not None:
        return redirect(url_for("main.dashboard"))
    form = {}
    if request.method == "POST":
        form = request.form
        (name, established, capital, revenue, cogs, opex, withdrawals), errors = collect_errors(
            clean_text(form.get("name"), "Shop name", 80),
            parse_date(form.get("established_on"), "Establishment date", allow_future=False),
            parse_amount(form.get("starting_capital"), "Starting capital"),
            parse_amount(form.get("revenue"), "Revenue", required=False),
            parse_amount(form.get("cogs"), "COGS", required=False),
            parse_amount(form.get("operating_expenses"), "Operating expenses", required=False),
            parse_amount(form.get("owner_withdrawals"), "Owner withdrawals", required=False),
        )
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            shop = Shop(user_id=current_user.id, name=name, established_on=established,
                        starting_capital=capital, initial_revenue=revenue, initial_cogs=cogs,
                        initial_operating_expenses=opex, initial_owner_withdrawals=withdrawals)
            db.session.add(shop)
            # Opening figures become ordinary records so everything is in one place.
            today = date.today()
            openings = [
                ("revenue", "Opening revenue", revenue),
                ("cogs", "Opening COGS", cogs),
                ("expense", "Opening operating expenses", opex),
                ("withdrawal", "Opening owner withdrawals", withdrawals),
            ]
            for kind, description, amount in openings:
                if amount > 0:
                    db.session.add(FinancialRecord(
                        user_id=current_user.id, category="Opening balance",
                        description=description, planned_amount=0, actual_amount=amount,
                        date=today, transaction_type=kind,
                        notes="Entered during shop setup"))
            db.session.commit()
            flash("Your shop is ready!", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("setup.html", form=form, today=date.today().isoformat())


@bp.route("/dashboard")
@shop_required
def dashboard():
    today = date.today()
    key = request.args.get("period", "all")
    if key not in dict(PERIOD_OPTIONS):
        key = "all"
    period = period_from_key(key, today)
    shop = current_user.shop

    metrics = finance.get_metrics(current_user.id, shop.starting_capital, ALL_TIME)
    period_metrics = finance.get_metrics(current_user.id, shop.starting_capital, period,
                                         include_capital=False)

    summary = queries.run_template("monthly_summary", current_user.id,
                                   start=ALL_TIME.start, end=ALL_TIME.end).as_dicts()[-12:]
    this_month = month_period(today.year, today.month)
    alerts = queries.run_template("budget_exceeded", current_user.id,
                                  start_month=this_month.start_month,
                                  end_month=this_month.end_month).as_dicts()
    recent = (FinancialRecord.query.filter_by(user_id=current_user.id)
              .order_by(FinancialRecord.date.desc(), FinancialRecord.id.desc()).limit(5).all())
    record_count = FinancialRecord.query.filter_by(user_id=current_user.id).count()

    return render_template("dashboard.html", shop=shop, metrics=metrics, period_metrics=period_metrics,
                           period=period, period_key=key, period_options=PERIOD_OPTIONS,
                           summary=summary, alerts=alerts, recent=recent, record_count=record_count)


@bp.route("/settings", methods=["GET", "POST"])
@shop_required
def settings():
    shop = current_user.shop
    if request.method == "POST":
        action = request.form.get("action")
        if action == "shop":
            (name, established, capital), errors = collect_errors(
                clean_text(request.form.get("name"), "Shop name", 80),
                parse_date(request.form.get("established_on"), "Establishment date",
                           allow_future=False),
                parse_amount(request.form.get("starting_capital"), "Starting capital"),
            )
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                shop.name, shop.established_on, shop.starting_capital = name, established, capital
                db.session.commit()
                flash("Shop details updated.", "success")
                return redirect(url_for("main.settings"))
        elif action == "password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            if not current_user.check_password(current):
                flash("Current password is wrong.", "danger")
            elif not 8 <= len(new) <= 128:
                flash("New password must be 8-128 characters.", "danger")
            elif new != request.form.get("confirm_password", ""):
                flash("New passwords do not match.", "danger")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Password changed.", "success")
                return redirect(url_for("main.settings"))
    return render_template("settings.html", shop=shop)
