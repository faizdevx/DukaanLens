"""Add, edit, delete, filter and export financial records."""
import csv
import io
from datetime import date

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user

from .extensions import db
from .models import TRANSACTION_TYPES, FinancialRecord
from .utils import shop_required
from .validators import clean_text, collect_errors, parse_amount, parse_date

bp = Blueprint("records", __name__, url_prefix="/records")


def filtered_query(args):
    """Build the records query from the filter form. Always limited to the current user."""
    query = FinancialRecord.query.filter_by(user_id=current_user.id)
    kind = args.get("type", "")
    if kind in TRANSACTION_TYPES:
        query = query.filter_by(transaction_type=kind)
    category = args.get("category", "").strip()
    if category:
        query = query.filter(db.func.lower(FinancialRecord.category) == category.lower())
    date_from, error = parse_date(args.get("date_from"), "From")
    if not error:
        query = query.filter(FinancialRecord.date >= date_from)
    date_to, error = parse_date(args.get("date_to"), "To")
    if not error:
        query = query.filter(FinancialRecord.date <= date_to)
    search = args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(FinancialRecord.description.ilike(like)
                             | FinancialRecord.notes.ilike(like))
    return query.order_by(FinancialRecord.date.desc(), FinancialRecord.id.desc())


def read_form(form):
    """Validate the record form. Returns (values dict, list of error messages)."""
    (category, description, planned, actual, when, notes), errors = collect_errors(
        clean_text(form.get("category"), "Category", 60),
        clean_text(form.get("description"), "Description", 200, required=False),
        parse_amount(form.get("planned_amount"), "Planned amount", required=False),
        parse_amount(form.get("actual_amount"), "Actual amount"),
        parse_date(form.get("date"), "Date"),
        clean_text(form.get("notes"), "Notes", 500, required=False),
    )
    kind = form.get("transaction_type", "")
    if kind not in TRANSACTION_TYPES:
        errors.append("Please choose a transaction type.")
    values = dict(category=category, description=description, planned_amount=planned,
                  actual_amount=actual, date=when, transaction_type=kind, notes=notes)
    return values, errors


def _user_record_or_404(record_id):
    record = FinancialRecord.query.filter_by(id=record_id, user_id=current_user.id).first()
    if record is None:
        abort(404)
    return record


@bp.route("/")
@shop_required
def list_records():
    records = filtered_query(request.args).all()
    categories = [c for (c,) in db.session.query(FinancialRecord.category)
                  .filter_by(user_id=current_user.id).distinct().order_by(FinancialRecord.category)]
    return render_template("records.html", records=records, categories=categories,
                           filters=request.args, has_filters=any(request.args.values()))


@bp.route("/new", methods=["GET", "POST"])
@shop_required
def create():
    form = {"date": date.today().isoformat(), "transaction_type": "expense"}
    if request.method == "POST":
        form = request.form
        values, errors = read_form(form)
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            db.session.add(FinancialRecord(user_id=current_user.id, **values))
            db.session.commit()
            flash("Record added.", "success")
            return redirect(url_for("records.list_records"))
    return render_template("record_form.html", form=form, record=None)


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
@shop_required
def edit(record_id):
    record = _user_record_or_404(record_id)
    form = {
        "category": record.category, "description": record.description,
        "planned_amount": record.planned_amount, "actual_amount": record.actual_amount,
        "date": record.date.isoformat(), "transaction_type": record.transaction_type,
        "notes": record.notes,
    }
    if request.method == "POST":
        form = request.form
        values, errors = read_form(form)
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            for key, value in values.items():
                setattr(record, key, value)
            db.session.commit()
            flash("Record updated.", "success")
            return redirect(url_for("records.list_records"))
    return render_template("record_form.html", form=form, record=record)


@bp.route("/<int:record_id>/delete", methods=["POST"])
@shop_required
def delete(record_id):
    record = _user_record_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    flash("Record deleted.", "info")
    return redirect(url_for("records.list_records"))


def _csv_safe(value):
    """Stop spreadsheet formula injection: a cell starting with = + - @ is a formula."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/export.csv")
@shop_required
def export_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "transaction_type", "category", "description",
                     "planned_amount", "actual_amount", "notes"])
    for r in filtered_query(request.args).all():
        writer.writerow([r.date.isoformat(), r.transaction_type, _csv_safe(r.category),
                         _csv_safe(r.description), r.planned_amount, r.actual_amount,
                         _csv_safe(r.notes)])
    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=dukaanlens_records.csv"})
