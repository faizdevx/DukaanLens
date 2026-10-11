from datetime import date

import pytest

from dukaanlens import create_app
from dukaanlens.extensions import db
from dukaanlens.models import FinancialRecord, Shop, User


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


class Client:
    """Test browser that automatically adds the CSRF token to every POST."""

    def __init__(self, flask_client):
        self.c = flask_client
        with self.c.session_transaction() as sess:
            sess["csrf_token"] = "test-token"

    def get(self, *a, **k):
        return self.c.get(*a, **k)

    def post(self, url, data=None, **k):
        data = dict(data or {})
        data.setdefault("csrf_token", "test-token")
        return self.c.post(url, data=data, **k)

    def post_json(self, url, payload):
        return self.c.post(url, json=payload, headers={"X-CSRF-Token": "test-token"})


@pytest.fixture()
def client(app):
    return Client(app.test_client())


def make_user(app, username="alice", password="password123", with_shop=True, capital=1000):
    with app.app_context():
        user = User(username=username, email=f"{username}@example.com")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        if with_shop:
            db.session.add(Shop(user_id=user.id, name=f"{username} shop",
                                established_on=date(2024, 1, 1), starting_capital=capital))
        db.session.commit()
        return user.id


def login(client, username="alice", password="password123"):
    return client.post("/login", {"identity": username, "password": password})


def add_record(app, user_id, kind, category, amount, when, planned=0, description=""):
    with app.app_context():
        db.session.add(FinancialRecord(user_id=user_id, transaction_type=kind, category=category,
                                       actual_amount=amount, planned_amount=planned, date=when,
                                       description=description))
        db.session.commit()
