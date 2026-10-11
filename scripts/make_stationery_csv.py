"""Generates sample_data/indian_stationery_products_4000.csv (deterministic, made-up data).

    python scripts/make_stationery_csv.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(2026)

# category -> (brands, product words, price range in INR)
CATALOG = {
    "Pens": (["Reynolds", "Cello", "Flair", "Linc", "Montex", "Pentonic"],
             ["Ball Pen Blue", "Gel Pen Black", "Fountain Pen", "Ink Pen Set", "Roller Pen Red"], (5, 180)),
    "Pencils": (["Natraj", "Apsara", "Doms", "Camlin"],
                ["HB Pencil Pack", "Colour Pencil 24", "Mechanical Pencil", "Charcoal Pencil"], (5, 150)),
    "Notebooks": (["Classmate", "Navneet", "Camlin", "Kokuyo"],
                  ["Long Notebook 172pg", "Spiral Notebook A4", "Drawing Book", "Register 200pg", "Diary 2026"],
                  (20, 320)),
    "Erasers & Sharpeners": (["Natraj", "Apsara", "Doms"],
                             ["Dust-Free Eraser", "Metal Sharpener", "Eraser Pack 10", "Double Hole Sharpener"],
                             (2, 60)),
    "Geometry Boxes": (["Camlin", "Classmate", "Saya", "Doms"],
                       ["Geometry Box Steel", "Compass Set", "Protractor 180", "Scale 30cm"], (30, 350)),
    "Art & Craft": (["Camlin", "Faber-Castell", "Fevicol", "Pidilite"],
                    ["Poster Colour Set", "Water Colour Cake 12", "Sketch Pens 24", "Crayons 48", "Clay Set"],
                    (25, 450)),
    "Files & Folders": (["Solo", "Kokuyo", "Bantex", "Navneet"],
                        ["Box File A4", "Clip File", "Zip Folder", "Ring Binder", "Document Wallet"], (15, 280)),
    "Adhesives": (["Fevicol", "Pidilite", "Camlin", "Dendrite"],
                  ["Glue Stick 15g", "Fevicol MR 50g", "Gum Bottle", "Fevistik", "Double Tape"], (10, 120)),
    "Paper": (["JK Paper", "ITC", "Navneet", "Classmate"],
              ["A4 Paper Ream 500", "Chart Paper Pack", "Sticky Notes", "Graph Paper Pad", "Carbon Paper"],
              (25, 520)),
    "Markers & Highlighters": (["Camlin", "Luxor", "Flair", "Cello"],
                               ["Permanent Marker", "Whiteboard Marker", "Highlighter 4", "Paint Marker"],
                               (15, 220)),
    "Office Supplies": (["Kangaro", "Maniks", "Omega", "Saya"],
                        ["Stapler Medium", "Staple Pins 24/6", "Paper Punch", "Scissors", "Pin Cushion"],
                        (20, 400)),
}
CITIES = ["Delhi", "Mumbai", "Kolkata", "Chennai", "Pune", "Jaipur", "Ahmedabad", "Lucknow"]
OUT = Path(__file__).resolve().parent.parent / "sample_data" / "indian_stationery_products_4000.csv"

OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["product_id", "product_name", "brand", "category", "unit_price_inr",
                     "stock_quantity", "supplier_city", "last_restocked", "rating"])
    start = date(2025, 1, 1)
    categories = list(CATALOG)
    for i in range(1, 4001):
        category = random.choice(categories)
        brands, words, (low, high) = CATALOG[category]
        brand, word = random.choice(brands), random.choice(words)
        price = round(random.uniform(low, high), 2)
        writer.writerow([
            f"STN{i:05d}", f"{brand} {word}", brand, category, price,
            random.randint(0, 600), random.choice(CITIES),
            (start + timedelta(days=random.randint(0, 650))).isoformat(),
            round(random.uniform(3.0, 5.0), 1),
        ])
print("wrote", OUT)
