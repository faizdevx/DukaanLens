"""The "Ask DukaanLens" chat page and its JSON endpoint."""
from datetime import date

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user

from . import ai_sql, apikeys
from .models import UploadedTable
from .utils import shop_required

bp = Blueprint("chat", __name__, url_prefix="/assistant")


@bp.route("/")
@shop_required
def page():
    tables = (UploadedTable.query.filter_by(user_id=current_user.id)
              .order_by(UploadedTable.display_name).all())
    table_info = [{"id": t.id, "name": t.display_name,
                   "columns": [f"{c['name']} ({c['type'].lower()})" for c in t.columns],
                   "suggestions": ai_sql.table_suggestions(t)} for t in tables]
    selected = request.args.get("source", "records")
    if selected not in {str(t.id) for t in tables}:
        selected = "records"
    api_key, _ = apikeys.get_credentials(current_user.id)
    return render_template("assistant.html", suggestions=ai_sql.SHOP_SUGGESTIONS,
                           tables=table_info, selected=selected, has_key=bool(api_key))


@bp.route("/ask", methods=["POST"])
@shop_required
def ask():
    payload = request.get_json(silent=True) or {}
    reply = ai_sql.answer_question(
        current_user.id, str(payload.get("source", "records")),
        str(payload.get("message", "")), date.today(), payload.get("history"))
    return jsonify(reply)
