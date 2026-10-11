"""Database models: users, shops, financial records and budgets."""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

# The four kinds of money movement we track.
TRANSACTION_TYPES = ["revenue", "cogs", "expense", "withdrawal"]
TYPE_LABELS = {
    "revenue": "Revenue",
    "cogs": "COGS (cost of goods sold)",
    "expense": "Operating expense",
    "withdrawal": "Owner withdrawal",
}


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    shop = db.relationship("Shop", back_populates="owner", uselist=False,
                           cascade="all, delete-orphan")
    records = db.relationship("FinancialRecord", back_populates="user",
                              cascade="all, delete-orphan")
    budgets = db.relationship("Budget", back_populates="user",
                              cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Shop(db.Model):
    """One shop per user. Holds the numbers typed in during first-time setup."""
    __tablename__ = "shops"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    established_on = db.Column(db.Date, nullable=False)
    starting_capital = db.Column(db.Float, nullable=False, default=0)
    # Opening figures from setup (copied into financial_records as opening entries).
    initial_revenue = db.Column(db.Float, nullable=False, default=0)
    initial_cogs = db.Column(db.Float, nullable=False, default=0)
    initial_operating_expenses = db.Column(db.Float, nullable=False, default=0)
    initial_owner_withdrawals = db.Column(db.Float, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    owner = db.relationship("User", back_populates="shop")


class FinancialRecord(db.Model):
    __tablename__ = "financial_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(200), nullable=False, default="")
    planned_amount = db.Column(db.Float, nullable=False, default=0)
    actual_amount = db.Column(db.Float, nullable=False, default=0)
    date = db.Column(db.Date, nullable=False, index=True)
    transaction_type = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", back_populates="records")

    @property
    def type_label(self):
        return TYPE_LABELS.get(self.transaction_type, self.transaction_type)


class Budget(db.Model):
    """A spending limit for one category in one month (month looks like 2026-03)."""
    __tablename__ = "budgets"
    __table_args__ = (db.UniqueConstraint("user_id", "category", "month",
                                          name="uq_budget_user_category_month"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", back_populates="budgets")
