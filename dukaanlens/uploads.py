"""Upload CSV files, list them, preview them, delete them."""
from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from . import csv_import, sandbox
from .models import UploadedTable
from .utils import shop_required
from .validators import clean_text

bp = Blueprint("uploads", __name__, url_prefix="/uploads")


def get_table_or_404(table_id):
    table = UploadedTable.query.filter_by(id=table_id, user_id=current_user.id).first()
    if table is None:
        abort(404)
    return table


@bp.route("/", methods=["GET", "POST"])
@shop_required
def list_uploads():
    if request.method == "POST":
        upload = request.files.get("file")
        name, error = clean_text(request.form.get("name"), "Table name", 60, required=False)
        if error:
            flash(error, "danger")
        elif upload is None or not upload.filename:
            flash("Please choose a CSV file.", "danger")
        elif not upload.filename.lower().endswith(".csv"):
            flash("Only .csv files are supported.", "danger")
        elif UploadedTable.query.filter_by(user_id=current_user.id).count() >= csv_import.MAX_TABLES_PER_USER:
            flash(f"You can keep at most {csv_import.MAX_TABLES_PER_USER} tables. Delete one first.",
                  "danger")
        else:
            display = name or Path(upload.filename).stem[:60] or "data"
            try:
                headers, rows = csv_import.parse_csv(upload.read())
                table = csv_import.store_table(current_user, display, upload.filename, headers, rows)
            except csv_import.CsvError as exc:
                flash(str(exc), "danger")
            else:
                flash(f"Imported {table.row_count:,} rows into table '{table.display_name}'.",
                      "success")
                return redirect(url_for("uploads.detail", table_id=table.id))
    tables = (UploadedTable.query.filter_by(user_id=current_user.id)
              .order_by(UploadedTable.created_at.desc()).all())
    return render_template("uploads.html", tables=tables, limits=csv_import)


@bp.route("/<int:table_id>")
@shop_required
def detail(table_id):
    table = get_table_or_404(table_id)
    columns, rows, _ = sandbox.run_select(
        f'SELECT * FROM "{table.table_name}" LIMIT 10', {table.table_name})
    return render_template("upload_detail.html", table=table, columns=columns, rows=rows)


@bp.route("/<int:table_id>/delete", methods=["POST"])
@shop_required
def delete(table_id):
    table = get_table_or_404(table_id)
    csv_import.drop_table(table)
    flash("Table deleted.", "info")
    return redirect(url_for("uploads.list_uploads"))
