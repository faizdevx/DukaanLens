"""Runs the whole user journey against a throw-away copy of the app and saves screenshots
to docs/screenshots/, plus the real Gemini answers to docs/example_run.json.

Needs: pip install playwright  (uses your installed Microsoft Edge, no browser download)
       GEMINI_API_KEY in the environment (used only by this temporary server)

    set GEMINI_API_KEY=...   (PowerShell: $env:GEMINI_API_KEY="...")
    python scripts/make_screenshots.py
"""
import csv
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
PORT = 5055
BASE = f"http://127.0.0.1:{PORT}"
PRODUCTS = ROOT / "sample_data" / "indian_stationery_products_4000.csv"
EXTRA_CSV = os.environ.get("EXTRA_CSV")        # optional second file to upload and query

ONLY_EXTRA = bool(os.environ.get("ONLY_EXTRA"))   # skip the product questions (saves quota)
QUESTIONS = [] if ONLY_EXTRA else [
    "How many products are there in total?",
    "What is the average price of Pens?",
    "Which brand has the highest total stock value (price times quantity)?",
    "Show the 5 most expensive products in Notebooks",
    "How many products have stock below 20, per category?",
]


def expected_answers():
    """Independent check of the answers, computed with plain Python."""
    with PRODUCTS.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    pens = [float(r["unit_price_inr"]) for r in rows if r["category"] == "Pens"]
    value = {}
    for r in rows:
        value[r["brand"]] = value.get(r["brand"], 0) + float(r["unit_price_inr"]) * int(r["stock_quantity"])
    best = max(value, key=value.get)
    notebooks = sorted((r for r in rows if r["category"] == "Notebooks"),
                       key=lambda r: -float(r["unit_price_inr"]))[:5]
    low = {}
    for r in rows:
        if int(r["stock_quantity"]) < 20:
            low[r["category"]] = low.get(r["category"], 0) + 1
    return {
        "count": len(rows),
        "avg_pen_price": round(sum(pens) / len(pens), 2),
        "top_brand_by_stock_value": [best, round(value[best], 2)],
        "top5_notebooks": [[r["product_name"], float(r["unit_price_inr"])] for r in notebooks],
        "low_stock_per_category": dict(sorted(low.items())),
    }


def wait_for_server():
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/login", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("server did not start")


def ask(page, text, results):
    """Asks one question. The free Gemini tier allows only a few requests per minute and each
    question uses two, so we wait and retry when the quota message comes back."""
    for attempt in range(4):
        before = page.locator(".bubble.bot").count()
        page.fill("#chat-message", text)
        with page.expect_response(lambda r: r.url.endswith("/assistant/ask")) as info:
            page.click("#chat-form button")
        reply = info.value.json()
        page.wait_for_function(
            "(n) => document.querySelectorAll('.bubble.bot').length > n && "
            "![...document.querySelectorAll('.bubble.bot')].some(b => b.textContent === 'Thinking...')",
            arg=before)
        if "rate limit" not in (reply.get("answer") or ""):
            break
        page.evaluate("() => { const l = document.getElementById('chat-log');"
                      " l.lastElementChild.remove(); l.lastElementChild.remove(); }")
        print("rate limited, waiting 65s ...", flush=True)
        time.sleep(65)
    time.sleep(35)   # stay under the free-tier requests-per-minute limit
    results.append({"question": text, "answer": reply.get("answer"), "sql": reply.get("sql"),
                    "columns": reply.get("columns"), "rows": (reply.get("rows") or [])[:10],
                    "notes": reply.get("notes")})


def main():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.")
    SHOTS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    env = dict(os.environ, SECRET_KEY=secrets.token_hex(32),
               DATABASE_URL=f"sqlite:///{(tmp / 'demo.db').as_posix()}")
    server = subprocess.Popen([sys.executable, "-m", "flask", "--app", "run", "run", "--port", str(PORT)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results, extra_results = [], []
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1280, "height": 800})

            # 1. sign up
            page.goto(BASE + "/register")
            page.fill("#username", "sharma_stationery")
            page.fill("#email", "sharma@example.com")
            page.fill("#password", "Stationery#2026")
            page.fill("#confirm", "Stationery#2026")
            page.screenshot(path=SHOTS / "01-register.png")
            page.click("button.btn-primary")

            # 2. shop setup with example details
            page.wait_for_url("**/setup")
            page.fill("#name", "Sharma Stationery Mart")
            page.fill("#established_on", "2021-04-01")
            page.fill("#starting_capital", "150000")
            page.fill("#revenue", "480000")
            page.fill("#cogs", "290000")
            page.fill("#operating_expenses", "95000")
            page.fill("#owner_withdrawals", "60000")
            page.screenshot(path=SHOTS / "02-shop-setup.png", full_page=True)
            page.click("button.btn-primary")

            # 3. dashboard
            page.wait_for_url("**/dashboard")
            page.wait_for_timeout(1200)
            page.screenshot(path=SHOTS / "03-dashboard.png", full_page=True)

            # 4. upload the CSV
            page.goto(BASE + "/uploads/")
            page.set_input_files("#file", str(PRODUCTS))
            page.fill("#name", "Stationery products")
            page.screenshot(path=SHOTS / "04-upload-csv.png", full_page=True)
            page.click("button.btn-primary")
            page.wait_for_url("**/uploads/*")
            table_id = page.url.rstrip("/").split("/")[-1]
            page.screenshot(path=SHOTS / "05-table-created.png", full_page=True)

            # 5. ask in plain English
            page.goto(f"{BASE}/assistant/?source={table_id}")
            for question in QUESTIONS:
                ask(page, question, results)
            page.evaluate("""() => {
                document.querySelectorAll('details').forEach(d => d.open = true);
                const log = document.getElementById('chat-log');
                log.style.height = 'auto'; log.style.maxHeight = 'none'; log.style.overflow = 'visible';
            }""")
            if QUESTIONS:
                page.screenshot(path=SHOTS / "06-ask-dukaanlens.png", full_page=True)

            # 6. optional second file (e.g. your own export)
            if EXTRA_CSV and Path(EXTRA_CSV).exists():
                page.goto(BASE + "/uploads/")
                page.set_input_files("#file", EXTRA_CSV)
                page.fill("#name", "My records export")
                page.click("button.btn-primary")
                page.wait_for_url("**/uploads/*")
                extra_id = page.url.rstrip("/").split("/")[-1]
                page.goto(f"{BASE}/assistant/?source={extra_id}")
                ask(page, "What is the total revenue minus COGS?", extra_results)
                page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                page.screenshot(path=SHOTS / "07-second-file.png", full_page=True)
            browser.close()
    finally:
        if sys.platform == "win32":      # the venv launcher spawns a child: kill the whole tree
            subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"],
                           capture_output=True)
        else:
            server.terminate()

    out = {"gemini_answers": results, "second_file": extra_results, "expected": expected_answers()}
    name = "example_run_second_file.json" if ONLY_EXTRA else "example_run.json"
    (ROOT / "docs" / name).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
