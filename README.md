# DukaanLens

A beginner-friendly finance dashboard for small shop owners. Track revenue, costs and budgets,
then ask questions about your own numbers in plain English.

**Stack:** Python, Flask, SQLite, SQLAlchemy, Flask-Login, Bootstrap, vanilla JavaScript.
One repository, one process, no Docker, no paid APIs.

## Features

- **Accounts:** register, log in, log out. Passwords are hashed. Every user sees only their own data.
- **Shop setup:** on first login enter shop name, establishment date, starting capital, revenue, COGS,
  operating expenses and owner withdrawals.
- **Dashboard:** revenue, COGS, gross profit, expenses, net profit, owner withdrawals, and a clearly
  labelled *estimated* cash figure. Monthly chart and budget alerts.
- **Financial records:** add, edit, delete, filter (type, category, dates, text) and export CSV.
- **Budget sheets:** a monthly limit per category, with spent / remaining / over-limit status.
- **Ask DukaanLens:** a chat that turns questions into approved, read-only SQL templates and shows
  the answer, the SQL used and the result rows.

## Setup

```bash
git clone https://github.com/faizdevx/DukaanLens.git
cd DukaanLens
python -m venv venv
# Windows:  venv\Scripts\activate        macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put a real SECRET_KEY inside
python run.py               # open http://127.0.0.1:5000
```

Optional demo data (user `demo`, password `demo12345`, six months of sample records and budgets):

```bash
flask --app run seed-demo
```

Run the tests:

```bash
python -m pytest
```

## How the numbers work

| Metric | Formula |
| --- | --- |
| Gross profit | Revenue − COGS |
| Net profit | Revenue − COGS − Operating expenses |
| Owner withdrawals | Tracked separately. **Not** an expense, never reduces profit |
| Estimated cash | Starting capital + Net profit − Owner withdrawals |

Estimated cash is only a guess: it assumes every sale was paid in cash and every cost was paid
immediately (no credit, no unpaid bills, no stock sitting on shelves).

The opening figures from shop setup are saved as ordinary records in category *Opening balance*,
so the dashboard and the assistant use one source of truth: the `financial_records` table.

### Transaction types

`revenue`, `cogs` (cost of goods sold, e.g. stock purchases), `expense` (operating expense),
`withdrawal` (owner takes money out).

## Ask DukaanLens: how it works

1. Keyword rules find the **intent** (expenses, profit, budget, ...).
2. A small parser finds the **period** ("last month", "this year", "March 2026", "all time").
3. Your own category names are matched in the sentence.
4. The matching **predefined SQL template** in [`dukaanlens/queries.py`](dukaanlens/queries.py) runs
   with bound parameters. Missing information triggers a follow-up question.

Questions it understands, for example:

- What were my total expenses last month?
- Which budget categories exceeded their limits?
- How much profit did I make this year?
- Show monthly revenue
- How much did I spend on inventory?
- Also: gross profit, owner withdrawals, estimated cash, biggest spending category, budget status.

Anything else gets an "I can't answer that" message with examples. User text is **never** turned
into SQL.

## Security notes

- Passwords hashed with Werkzeug; secrets (`SECRET_KEY`, `DATABASE_URL`) come from environment
  variables / `.env` (git-ignored).
- All queries filter by the logged-in user's id; records and budgets are looked up with their owner's
  id, so other users' ids return 404.
- Assistant queries are fixed read-only `SELECT` templates, checked at import time (no writes, no
  semicolons, must filter by `:user_id`).
- CSRF token on every POST, form validation on every input, CSV export neutralises spreadsheet
  formulas, redirects after login are restricted to local paths.

## Project layout

```
run.py                    start the app
dukaanlens/
  __init__.py             app factory, CSRF, config
  models.py               User, Shop, FinancialRecord, Budget
  auth.py main.py records.py budgets.py chat.py   routes (blueprints)
  finance.py              profit / cash calculations
  queries.py              approved read-only SQL templates
  assistant.py periods.py intent + period parsing
  seed.py                 demo data
  templates/ static/      Bootstrap UI, CSS, JS
tests/                    pytest: auth, data isolation, finance, assistant
```

## Limitations

Amounts are stored as floats (fine for learning; use integer paise or `Decimal` for real
accounting). The assistant is rule-based, so it understands a limited set of phrasings.
