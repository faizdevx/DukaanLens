"""Regenerates sample_data/sales_sample.csv (deterministic):  python tests/make_sample.py"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
products = {"Rice 5kg": ("Grocery", 320), "Atta 10kg": ("Grocery", 410), "Notebook": ("Stationery", 45),
            "Pen Pack": ("Stationery", 60), "Soap": ("Personal Care", 38), "Shampoo": ("Personal Care", 120),
            "Tea 500g": ("Grocery", 215), "Biscuits": ("Snacks", 25)}
cities = ["Delhi", "Mumbai", "Pune", "Jaipur"]
out = Path(__file__).resolve().parent.parent / "sample_data" / "sales_sample.csv"
out.parent.mkdir(exist_ok=True)
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Order Date", "Product", "Category", "City", "Quantity", "Unit Price", "Amount"])
    start = date(2025, 1, 1)
    for i in range(120):
        product = random.choice(list(products))
        category, price = products[product]
        qty = random.randint(1, 10)
        w.writerow([(start + timedelta(days=i * 3)).isoformat(), product, category,
                    random.choice(cities), qty, price, qty * price])
print("wrote", out)
