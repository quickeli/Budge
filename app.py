from flask import Flask, request, render_template_string, Response
import csv
import io
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from config import ensure_config, save_config, CONFIG_PATH
from database import (
    add_tx,
    list_txs,
    get_tx,
    update_tx,
    delete_tx,
    unsynced_txs,
    mark_synced,
    monthly_summary,
    get_db,
    init_app,
    DB_PATH,
)
from utils import to_cents, cents_to_str

app = Flask(__name__)
init_app(app)

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Budge - Personal Finance Tracker</title>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-color: #2563eb;
            --primary-hover: #1d4ed8;
            --secondary-color: #64748b;
            --success-color: #10b981;
            --danger-color: #ef4444;
            --background: #f8fafc;
            --surface: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--background);
            color: var(--text-primary);
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 1rem;
        }

        .header {
            background: var(--surface);
            box-shadow: var(--shadow);
            margin-bottom: 2rem;
            border-radius: 0.75rem;
            padding: 1.5rem;
        }

        .header h1 {
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary-color);
            margin-bottom: 0.5rem;
        }

        .header p {
            color: var(--text-secondary);
            font-size: 0.875rem;
        }

        .grid {
            display: grid;
            gap: 1.5rem;
            grid-template-columns: 1fr;
        }

        @media (min-width: 768px) {
            .grid {
                grid-template-columns: 2fr 1fr;
            }
        }

        @media (min-width: 1024px) {
            .grid {
                grid-template-columns: 2fr 1fr 1fr;
            }
        }

        .card {
            background: var(--surface);
            border-radius: 0.75rem;
            box-shadow: var(--shadow);
            overflow: hidden;
        }

        .card-header {
            padding: 1.5rem 1.5rem 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 1.5rem;
        }

        .card-header h2 {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .card-content {
            padding: 0 1.5rem 1.5rem;
        }

        .transactions-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }

        .transactions-table th,
        .transactions-table td {
            padding: 0.75rem 0.5rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        .transactions-table th {
            background-color: var(--background);
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .transactions-table tr:hover {
            background-color: var(--background);
        }

        .amount-positive {
            color: var(--success-color);
            font-weight: 600;
        }

        .amount-negative {
            color: var(--danger-color);
            font-weight: 600;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .badge-expense {
            background-color: #fef2f2;
            color: var(--danger-color);
        }

        .badge-income {
            background-color: #f0fdf4;
            color: var(--success-color);
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
        }

        .btn-primary {
            background-color: var(--primary-color);
            color: white;
        }

        .btn-primary:hover {
            background-color: var(--primary-hover);
        }

        .btn-secondary {
            background-color: var(--secondary-color);
            color: white;
        }

        .btn-secondary:hover {
            background-color: #475569;
        }

        .btn-danger {
            background-color: var(--danger-color);
            color: white;
        }

        .btn-danger:hover {
            background-color: #dc2626;
        }

        .btn-sm {
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        .form-label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }

        .form-input,
        .form-select {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            font-size: 0.875rem;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        .form-input:focus,
        .form-select:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgb(37 99 235 / 0.1);
        }

        .month-selector {
            margin-bottom: 1rem;
        }

        .actions {
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }

        .budget-table {
            width: 100%;
            font-size: 0.875rem;
        }

        .budget-table th,
        .budget-table td {
            padding: 0.75rem 0.5rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        .budget-table th {
            background-color: var(--background);
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
        }

        .budget-input {
            width: 100%;
            padding: 0.5rem;
            border: 1px solid var(--border-color);
            border-radius: 0.375rem;
            font-size: 0.875rem;
        }

        .budget-remaining {
            font-weight: 600;
        }

        .budget-remaining.positive {
            color: var(--success-color);
        }

        .budget-remaining.negative {
            color: var(--danger-color);
        }

        .toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
        }

        /* Mobile optimizations */
        @media (max-width: 767px) {
            .container {
                padding: 0.5rem;
            }

            .header {
                padding: 1rem;
                margin-bottom: 1rem;
            }

            .header h1 {
                font-size: 1.5rem;
            }

            .card-header,
            .card-content {
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .transactions-table {
                font-size: 0.75rem;
            }

            .transactions-table th,
            .transactions-table td {
                padding: 0.5rem 0.25rem;
            }

            .actions {
                flex-direction: column;
                align-items: stretch;
            }

            .actions .btn {
                justify-content: center;
            }
        }

        .htmx-request {
            opacity: 0.7;
            transition: opacity 0.2s;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1><i class="fas fa-wallet"></i> Budge</h1>
            <p>Your personal finance tracker</p>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-list"></i> Transactions</h2>
                </div>
                <div class="card-content">
                    <div id="transactions-table">
                        <div class="month-selector">
                            <input type="month" name="month" value="{{ month }}" 
                                   class="form-input" 
                                   hx-get="/txs_partial" 
                                   hx-target="#transactions-table" 
                                   hx-swap="outerHTML">
                        </div>
                        <div style="overflow-x: auto;">
                            <table class="transactions-table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Amount</th>
                                        <th>Type</th>
                                        <th>Category</th>
                                        <th>Description</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for tx in txs %}
                                    <tr id="tx-{{ tx.id }}">
                                        <td>{{ tx.iso_date }}</td>
                                        <td class="{% if tx.type == 'income' %}amount-positive{% else %}amount-negative{% endif %}">
                                            {% if tx.type == 'income' %}+{% else %}-{% endif %}${{ cents_to_str(tx.amount_cents) }}
                                        </td>
                                        <td>
                                            <span class="badge badge-{{ tx.type }}">
                                                {% if tx.type == 'income' %}<i class="fas fa-arrow-up"></i>{% else %}<i class="fas fa-arrow-down"></i>{% endif %}
                                                {{ tx.type.title() }}
                                            </span>
                                        </td>
                                        <td>{{ tx.category }}</td>
                                        <td>{{ tx.description }}</td>
                                        <td>
                                            <div class="actions">
                                                <button class="btn btn-sm btn-secondary" 
                                                        hx-get="/edit_form/{{ tx.id }}" 
                                                        hx-target="#tx-{{ tx.id }}" 
                                                        hx-swap="outerHTML">
                                                    <i class="fas fa-edit"></i> Edit
                                                </button>
                                                <button class="btn btn-sm btn-danger" 
                                                        hx-delete="/delete/{{ tx.id }}" 
                                                        hx-target="#tx-{{ tx.id }}" 
                                                        hx-swap="outerHTML"
                                                        hx-confirm="Are you sure you want to delete this transaction?">
                                                    <i class="fas fa-trash"></i> Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-chart-pie"></i> Budgets</h2>
                </div>
                <div class="card-content">
                    <div id="budgets-table">
                        <form hx-post="/save_budgets" hx-target="#budgets-table" hx-swap="outerHTML">
                            <table class="budget-table">
                                <thead>
                                    <tr>
                                        <th>Category</th>
                                        <th>Budget</th>
                                        <th>Actual</th>
                                        <th>Remaining</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for cat in categories %}
                                    <tr>
                                        <td>{{ cat }}</td>
                                        <td>
                                            <input type="text" name="{{ cat }}" 
                                                   class="budget-input" 
                                                   value="{{ cents_to_str(budgets.get(cat, 0)) }}" 
                                                   placeholder="0.00">
                                        </td>
                                        <td class="{% if summary.get(cat, 0) > 0 %}amount-negative{% endif %}">
                                            ${{ cents_to_str(summary.get(cat, 0)) }}
                                        </td>
                                        <td class="budget-remaining {% if (budgets.get(cat, 0) - summary.get(cat, 0)) >= 0 %}positive{% else %}negative{% endif %}">
                                            ${{ cents_to_str(budgets.get(cat, 0) - summary.get(cat, 0)) }}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                            <div style="margin-top: 1rem;">
                                <button type="submit" class="btn btn-primary">
                                    <i class="fas fa-save"></i> Save Budgets
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-plus"></i> Add Transaction</h2>
                </div>
                <div class="card-content">
                    <form hx-post="/add" hx-target="#transactions-table" hx-swap="outerHTML">
                        <div class="form-group">
                            <label class="form-label">Date</label>
                            <input type="date" name="date" value="{{ month }}-01" class="form-input" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Amount</label>
                            <input type="text" name="amount" placeholder="0.00" class="form-input" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Type</label>
                            <select name="type" class="form-select" required>
                                <option value="expense">Expense</option>
                                <option value="income">Income</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Category</label>
                            <select name="category" class="form-select" required>
                                {% for cat in categories %}
                                <option value="{{ cat }}">{{ cat }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <input type="text" name="description" placeholder="Enter description" class="form-input">
                        </div>
                        <button type="submit" class="btn btn-primary" style="width: 100%;">
                            <i class="fas fa-plus"></i> Add Transaction
                        </button>
                    </form>

                    <div class="toolbar">
                        <a href="/export" class="btn btn-secondary">
                            <i class="fas fa-download"></i> Export CSV
                        </a>
                        <button class="btn btn-secondary" hx-get="/sync">
                            <i class="fas fa-sync"></i> Sync
                        </button>
                        <form hx-post="/clear_all" hx-target="#transactions-table" hx-swap="outerHTML" style="display: inline-block;">
                            <button type="submit" class="btn btn-danger" 
                                    onclick="return confirm('Are you sure you want to delete all transactions?')">
                                <i class="fas fa-trash-alt"></i> Clear All
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

TXS_PARTIAL = """
<div id="transactions-table">
    <div class="month-selector">
        <input type="month" name="month" value="{{ month }}" 
               class="form-input" 
               hx-get="/txs_partial" 
               hx-target="#transactions-table" 
               hx-swap="outerHTML">
    </div>
    <div style="overflow-x: auto;">
        <table class="transactions-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Amount</th>
                    <th>Type</th>
                    <th>Category</th>
                    <th>Description</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for tx in txs %}
                <tr id="tx-{{ tx.id }}">
                    <td>{{ tx.iso_date }}</td>
                    <td class="{% if tx.type == 'income' %}amount-positive{% else %}amount-negative{% endif %}">
                        {% if tx.type == 'income' %}+{% else %}-{% endif %}${{ cents_to_str(tx.amount_cents) }}
                    </td>
                    <td>
                        <span class="badge badge-{{ tx.type }}">
                            {% if tx.type == 'income' %}<i class="fas fa-arrow-up"></i>{% else %}<i class="fas fa-arrow-down"></i>{% endif %}
                            {{ tx.type.title() }}
                        </span>
                    </td>
                    <td>{{ tx.category }}</td>
                    <td>{{ tx.description }}</td>
                    <td>
                        <div class="actions">
                            <button class="btn btn-sm btn-secondary" 
                                    hx-get="/edit_form/{{ tx.id }}" 
                                    hx-target="#tx-{{ tx.id }}" 
                                    hx-swap="outerHTML">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            <button class="btn btn-sm btn-danger" 
                                    hx-delete="/delete/{{ tx.id }}" 
                                    hx-target="#tx-{{ tx.id }}" 
                                    hx-swap="outerHTML"
                                    hx-confirm="Are you sure you want to delete this transaction?">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
"""

BUDGETS_PARTIAL = """
<div id="budgets-table">
    <form hx-post="/save_budgets" hx-target="#budgets-table" hx-swap="outerHTML">
        <table class="budget-table">
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Budget</th>
                    <th>Actual</th>
                    <th>Remaining</th>
                </tr>
            </thead>
            <tbody>
                {% for cat in categories %}
                <tr>
                    <td>{{ cat }}</td>
                    <td>
                        <input type="text" name="{{ cat }}" 
                               class="budget-input" 
                               value="{{ cents_to_str(budgets.get(cat, 0)) }}" 
                               placeholder="0.00">
                    </td>
                    <td class="{% if summary.get(cat, 0) > 0 %}amount-negative{% endif %}">
                        ${{ cents_to_str(summary.get(cat, 0)) }}
                    </td>
                    <td class="budget-remaining {% if (budgets.get(cat, 0) - summary.get(cat, 0)) >= 0 %}positive{% else %}negative{% endif %}">
                        ${{ cents_to_str(budgets.get(cat, 0) - summary.get(cat, 0)) }}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div style="margin-top: 1rem;">
            <button type="submit" class="btn btn-primary">
                <i class="fas fa-save"></i> Save Budgets
            </button>
        </div>
    </form>
</div>
"""

EDIT_FORM_PARTIAL = """
<tr id="tx-{{ tx.id }}" style="background-color: var(--background);">
    <td colspan="6">
        <form hx-post="/edit/{{ tx.id }}" hx-target="#transactions-table" hx-swap="outerHTML" 
              style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.5rem; padding: 1rem;">
            <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label" style="font-size: 0.75rem;">Date</label>
                <input type="date" name="date" value="{{ tx.iso_date }}" class="form-input" style="padding: 0.5rem;">
            </div>
            <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label" style="font-size: 0.75rem;">Amount</label>
                <input type="text" name="amount" value="{{ cents_to_str(tx.amount_cents) }}" class="form-input" style="padding: 0.5rem;">
            </div>
            <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label" style="font-size: 0.75rem;">Type</label>
                <select name="type" class="form-select" style="padding: 0.5rem;">
                    <option value="expense" {% if tx.type == 'expense' %}selected{% endif %}>Expense</option>
                    <option value="income" {% if tx.type == 'income' %}selected{% endif %}>Income</option>
                </select>
            </div>
            <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label" style="font-size: 0.75rem;">Category</label>
                <select name="category" class="form-select" style="padding: 0.5rem;">
                    {% for cat in categories %}
                    <option value="{{ cat }}" {% if tx.category == cat %}selected{% endif %}>{{ cat }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label" style="font-size: 0.75rem;">Description</label>
                <input type="text" name="description" value="{{ tx.description }}" class="form-input" style="padding: 0.5rem;">
            </div>
            <div class="form-group" style="margin-bottom: 0; display: flex; align-items: end; gap: 0.5rem;">
                <button type="submit" class="btn btn-primary btn-sm">
                    <i class="fas fa-save"></i> Save
                </button>
                <button type="button" class="btn btn-secondary btn-sm" 
                        hx-get="/txs_partial" hx-target="#transactions-table" hx-swap="outerHTML">
                    <i class="fas fa-times"></i> Cancel
                </button>
            </div>
        </form>
    </td>
</tr>
"""

@app.route("/")
def index():
    cfg = ensure_config()
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    txs = list_txs(month_prefix=month)
    summary = monthly_summary(month_prefix=month)
    return render_template_string(
        BASE_HTML,
        txs=txs,
        month=month,
        categories=cfg["categories"],
        budgets=cfg.get("budgets", {}),
        summary=summary,
        cents_to_str=cents_to_str,
    )

@app.route("/txs_partial")
def txs_partial():
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    txs = list_txs(month_prefix=month)
    return render_template_string(TXS_PARTIAL, txs=txs, month=month, cents_to_str=cents_to_str)

@app.route("/add", methods=["POST"])
def add():
    form = request.form
    add_tx(
        form["date"],
        to_cents(form["amount"]),
        form["type"],
        form["category"],
        form["description"],
    )
    return txs_partial()

@app.route("/delete/<int:txid>", methods=["DELETE"])
def delete(txid):
    delete_tx(txid)
    return ""

@app.route("/edit_form/<int:txid>")
def edit_form(txid):
    tx = get_tx(txid)
    cfg = ensure_config()
    return render_template_string(EDIT_FORM_PARTIAL, tx=tx, categories=cfg["categories"], cents_to_str=cents_to_str)

@app.route("/edit/<int:txid>", methods=["POST"])
def edit(txid):
    form = request.form
    update_tx(
        txid,
        form["date"],
        to_cents(form["amount"]),
        form["type"],
        form["category"],
        form["description"],
    )
    return txs_partial()

@app.route("/save_budgets", methods=["POST"])
def save_budgets():
    cfg = ensure_config()
    budgets = {}
    for cat in cfg["categories"]:
        if cat in request.form:
            budgets[cat] = to_cents(request.form[cat])
    cfg["budgets"] = budgets
    save_config(cfg)
    summary = monthly_summary(month_prefix=datetime.now().strftime("%Y-%m"))
    return render_template_string(
        BUDGETS_PARTIAL,
        categories=cfg["categories"],
        budgets=cfg["budgets"],
        summary=summary,
        cents_to_str=cents_to_str,
    )

@app.route("/export")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Amount", "Type", "Category", "Description"])
    
    txs = list_txs()
    for tx in txs:
        writer.writerow([
            tx["iso_date"],
            cents_to_str(tx["amount_cents"]),
            tx["type"],
            tx["category"],
            tx["description"]
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"}
    )

@app.route("/sync")
def sync():
    cfg = ensure_config()
    firebase_url = cfg.get("firebase_url")
    if not firebase_url or not REQUESTS_AVAILABLE:
        return "Sync not configured or requests unavailable"
    
    unsynced = unsynced_txs()
    if unsynced:
        try:
            response = requests.post(firebase_url, json=unsynced)
            if response.status_code == 200:
                mark_synced([tx["id"] for tx in unsynced])
                return "Synced"
            else:
                return f"Sync failed: {response.status_code}"
        except Exception as e:
            return f"Sync error: {e}"
    return "Nothing to sync"

@app.route("/clear_all", methods=["POST"])
def clear_all():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    conn.commit()
    return txs_partial()

if __name__ == "__main__":
    ensure_config()
    print("Starting Budge (Flask + HTMX). DB:", DB_PATH, "Config:", CONFIG_PATH)
    app.run(host="0.0.0.0", port=8000, debug=True)