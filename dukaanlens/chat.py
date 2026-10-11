"""The "Ask DukaanLens" chat page and its JSON endpoint."""
from datetime import date

from flask import Blueprint, jsonify, render_template, request, session

from .assistant import SUGGESTIONS, answer_question
from .utils import shop_required
from flask_login import current_user

bp = Blueprint("chat", __name__, url_prefix="/assistant")


@bp.route("/")
@shop_required
def page():
    return render_template("assistant.html", suggestions=SUGGESTIONS)


@bp.route("/ask", methods=["POST"])
@shop_required
def ask():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", ""))
    reply = answer_question(current_user.id, message, date.today(),
                            pending=session.get("assistant_pending"))
    # Remember an open clarification question so the next message can answer it.
    session["assistant_pending"] = reply.get("pending")
    return jsonify(reply)
