"""Budget sheets: a spending limit per category per month."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from . import queries
from .extensions import db
from .models import Budget
from .periods import month_period
from .utils import shop_required
from .validators import clean_text, collect_errors, parse_amount, parse_month

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _budget_or_404(budget_id):
    budget = Budget.query.filter_by(id=budget_id, user_id=current_user.id).first()
    if budget is None:
        abort(404)
    return budget


def _read_form(form, existing_id=None):
    (category, month, limit, notes), errors = collect_errors(
        clean_text(form.get("category"), "Category", 60),
        parse_month(form.get("month"), "Month"),
        parse_amount(form.get("limit_amount"), "Limit"),
        clean_text(form.get("notes"), "Notes", 500, required=False),
    )
    if not errors:
        clash = Budget.query.filter(
            Budget.user_id == current_user.id, Budget.month == month,
            db.func.lower(Budget.category) == category.lower())
        if existing_id:
            clash = clash.filter(Budget.id != existing_id)
        if clash.first():
            errors.append(f"A budget for {category} in {month} already exists.")
    return dict(category=category, month=month, limit_amount=limit, notes=notes), errors


@bp.route("/", methods=["GET", "POST"])
@shop_required
def list_budgets():
    today = date.today()
    form = {}
    if request.method == "POST":
        form = request.form
        values, errors = _read_form(form)
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            db.session.add(Budget(user_id=current_user.id, **values))
            db.session.commit()
            flash("Budget added.", "success")
            return redirect(url_for("budgets.list_budgets", month=values["month"]))

    month, error = parse_month(request.args.get("month", today.strftime("%Y-%m")), "Month")
    if error:
        month = today.strftime("%Y-%m")
    year, mon = int(month[:4]), int(month[5:])
    status = queries.run_template("budget_status", current_user.id,
                                  start_month=month, end_month=month).as_dicts()
    spent_by_category = {row["category"].lower(): row["spent"] for row in status}
    budgets = (Budget.query.filter_by(user_id=current_user.id, month=month)
               .order_by(Budget.category).all())
    rows = []
    for budget in budgets:
        spent = spent_by_category.get(budget.category.lower(), 0)
        percent = round(spent / budget.limit_amount * 100) if budget.limit_amount else 0
        rows.append({"budget": budget, "spent": spent, "percent": percent,
                     "remaining": round(budget.limit_amount - spent, 2),
                     "over": spent > budget.limit_amount})
    prev_year, prev_mon = (year - 1, 12) if mon == 1 else (year, mon - 1)
    next_year, next_mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return render_template(
        "budgets.html", rows=rows, month=month, month_label=month_period(year, mon).label,
        prev_month=f"{prev_year}-{prev_mon:02d}", next_month=f"{next_year}-{next_mon:02d}",
        form=form or {"month": month})


@bp.route("/<int:budget_id>/edit", methods=["GET", "POST"])
@shop_required
def edit(budget_id):
    budget = _budget_or_404(budget_id)
    form = {"category": budget.category, "month": budget.month,
            "limit_amount": budget.limit_amount, "notes": budget.notes}
    if request.method == "POST":
        form = request.form
        values, errors = _read_form(form, existing_id=budget.id)
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            for key, value in values.items():
                setattr(budget, key, value)
            db.session.commit()
            flash("Budget updated.", "success")
            return redirect(url_for("budgets.list_budgets", month=budget.month))
    return render_template("budget_form.html", form=form, budget=budget)


@bp.route("/<int:budget_id>/delete", methods=["POST"])
@shop_required
def delete(budget_id):
    budget = _budget_or_404(budget_id)
    month = budget.month
    db.session.delete(budget)
    db.session.commit()
    flash("Budget deleted.", "info")
    return redirect(url_for("budgets.list_budgets", month=month))
