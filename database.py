import sqlite3
import os
from flask import g

APP_DIR = os.path.dirname(os.path.realpath(__file__))
DB_PATH = os.path.join(APP_DIR, "budget.db")

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        # if DB is empty, init
        cur = db.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            init_db(db)
    return db

def init_db(conn):
    cur = conn.cursor()
    cur.execute(
        """
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iso_date TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        type TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        synced BOOLEAN DEFAULT FALSE
    )
    """
    )
    conn.commit()

def add_tx(iso_date, amount_cents, ttype, category, description):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (iso_date, amount_cents, type, category, description, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (iso_date, amount_cents, ttype, category, description),
    )
    conn.commit()

def list_txs(limit=500, month_prefix=None):
    conn = get_db()
    cur = conn.cursor()
    if month_prefix:
        cur.execute("SELECT * FROM transactions WHERE iso_date LIKE ? ORDER BY iso_date DESC, id DESC LIMIT ?", (f"{month_prefix}%", limit))
    else:
        cur.execute("SELECT * FROM transactions ORDER BY iso_date DESC, id DESC LIMIT ?", (limit,))
    return cur.fetchall()

def get_tx(txid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id = ?", (txid,))
    return cur.fetchone()

def update_tx(txid, iso_date, amount_cents, ttype, category, description):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE transactions SET iso_date = ?, amount_cents = ?, type = ?, category = ?, description = ? WHERE id = ?",
        (iso_date, amount_cents, ttype, category, description, txid),
    )
    conn.commit()

def delete_tx(txid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id = ?", (txid,))
    conn.commit()

def unsynced_txs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE synced = FALSE")
    return cur.fetchall()

def mark_synced(ids):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"UPDATE transactions SET synced = TRUE WHERE id IN ({','.join('?' for _ in ids)})", ids)
    conn.commit()

def monthly_summary(month_prefix):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT category, SUM(amount_cents) FROM transactions WHERE iso_date LIKE ? AND type = 'expense' GROUP BY category",
        (f"{month_prefix}%",),
    )
    # in form of {'Groceries': 500, 'Restaurants': 300, etc.}
    return {row[0]: row[1] for row in cur.fetchall()}

def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)
