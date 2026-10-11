"""Demo data so you can try DukaanLens quickly:  flask --app run seed-demo"""
from datetime import date, timedelta

from .extensions import db
from .models import Budget, FinancialRecord, Shop, User

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"


def _month_start(today, months_back):
    year, month = today.year, today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def seed_demo(today=None):
    today = today or date.today()
    if User.query.filter_by(username=DEMO_USERNAME).first():
        return f"Demo user '{DEMO_USERNAME}' already exists."

    user = User(username=DEMO_USERNAME, email=DEMO_EMAIL)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()

    db.session.add(Shop(user_id=user.id, name="Sharma General Store",
                        established_on=today - timedelta(days=900), starting_capital=100000))

    # (type, category, description, planned, base actual)
    monthly = [
        ("revenue", "Sales", "Counter sales", 60000, 62000),
        ("revenue", "Sales", "Online orders", 10000, 9000),
        ("cogs", "Inventory", "Stock purchase", 35000, 37000),
        ("expense", "Rent", "Shop rent", 8000, 8000),
        ("expense", "Salaries", "Helper salary", 9000, 9000),
        ("expense", "Electricity", "Power bill", 1500, 1800),
        ("expense", "Transport", "Delivery & transport", 2000, 2600),
        ("withdrawal", "Owner withdrawal", "Household use", 10000, 10000),
    ]
    for months_back in range(5, -1, -1):
        start = _month_start(today, months_back)
        for i, (kind, category, description, planned, actual) in enumerate(monthly):
            wobble = 1 + ((months_back + i) % 4 - 1) * 0.05
            db.session.add(FinancialRecord(
                user_id=user.id, category=category, description=description,
                planned_amount=planned, actual_amount=round(actual * wobble, 2),
                date=start + timedelta(days=min(3 + i * 3, 27)), transaction_type=kind,
                notes="Sample data"))
        for category, limit in [("Inventory", 36000), ("Electricity", 1600),
                                ("Transport", 2200), ("Rent", 8000)]:
            db.session.add(Budget(user_id=user.id, category=category,
                                  month=start.strftime("%Y-%m"), limit_amount=limit))
    db.session.commit()
    return (f"Created demo user '{DEMO_USERNAME}' (password: {DEMO_PASSWORD}) "
            "with sample records and budgets.")
