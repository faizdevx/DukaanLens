from functools import wraps

from flask import redirect, url_for
from flask_login import current_user, login_required


def shop_required(view):
    """Login needed, and the shop must be set up (first-login wizard) first."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.shop is None:
            return redirect(url_for("main.setup"))
        return view(*args, **kwargs)
    return wrapped
