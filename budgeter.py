#!/usr/bin/env python3
"""
budgeter.py

Simple CLI budget/expense tracker:
- Local storage: SQLite (~/.budgeter/budget.db)
- Cloud sync (optional):
    * Firebase Realtime Database (easy REST push) -- set FIREBASE_URL in config
    * Google Sheets (requires service account json) -- set GOOGLE_SERVICE_ACCOUNT_FILE & GOOGLE_SHEET_NAME in config

Usage:
    python budgeter.py            # interactive menu
    python budgeter.py --help     # usage
"""

import os
import sqlite3
import json
import csv
import sys
import argparse
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
import requests
from dateutil import parser as dateparser  # pip install python-dateutil

# Optional imports for Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GS_AVAILABLE = True
except Exception:
    GS_AVAILABLE = False

# --- Constants & paths ---
HOME = os.path.expanduser("~")
APP_DIR = os.path.join(HOME, ".budgeter")
DB_PATH = os.path.join(APP_DIR, "budget.db")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CSV_EXPORT_PATH = os.path.join(APP_DIR, "export.csv")

# Ensure data dir exists
os.makedirs(APP_DIR, exist_ok=True)

# --- Utilities for money handling ---
def to_cents(amount_str: str) -> int:
    """
    Convert a user-entered amount string (like "12.34" or "12") to integer cents.
    Uses Decimal for safety.
    """
    dec = Decimal(amount_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cents = int((dec * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return cents

def cents_to_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents_abs = abs(cents)
    dollars = cents_abs // 100
    rem = cents_abs % 100
    return f"{sign}{dollars}.{rem:02d}"

# --- Database layer ---
class BudgetDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iso_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            type TEXT NOT NULL,          -- 'expense' or 'income'
            category TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            synced INTEGER DEFAULT 0     -- 0 = not synced to cloud, 1 = synced
        );
        """)
        self.conn.commit()

    def add_transaction(self, iso_date: str, amount_cents: int, ttype: str,
                        category: Optional[str], description: Optional[str]) -> int:
        cur = self.conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute("""
            INSERT INTO transactions (iso_date, amount_cents, type, category, description, created_at, synced)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (iso_date, amount_cents, ttype, category or "", description or "", now))
        self.conn.commit()
        return cur.lastrowid

    def list_transactions(self, limit=100) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, iso_date, amount_cents, type, category, description, created_at, synced FROM transactions ORDER BY iso_date DESC, id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row):
        return {
            "id": row[0],
            "iso_date": row[1],
            "amount_cents": row[2],
            "type": row[3],
            "category": row[4],
            "description": row[5],
            "created_at": row[6],
            "synced": bool(row[7])
        }

    def find_transactions(self, start_date=None, end_date=None, category=None) -> List[Dict]:
        cur = self.conn.cursor()
        query = "SELECT id, iso_date, amount_cents, type, category, description, created_at, synced FROM transactions WHERE 1=1"
        params = []
        if start_date:
            query += " AND iso_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND iso_date <= ?"
            params.append(end_date)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY iso_date DESC"
        cur.execute(query, params)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def monthly_summary(self, year: int, month: int) -> Dict[str, int]:
        start = date(year, month, 1).isoformat()
        if month == 12:
            end = date(year + 1, 1, 1).isoformat()
        else:
            end = date(year, month + 1, 1).isoformat()
        cur = self.conn.cursor()
        cur.execute("""
            SELECT type, SUM(amount_cents) FROM transactions
            WHERE iso_date >= ? AND iso_date < ?
            GROUP BY type
        """, (start, end))
        rows = cur.fetchall()
        result = {"income": 0, "expense": 0}
        for r in rows:
            ttype, s = r
            result[ttype] = s or 0
        return result

    def export_csv(self, csv_path=CSV_EXPORT_PATH):
        rows = self.list_transactions(limit=1000000)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "iso_date", "amount", "type", "category", "description", "created_at", "synced"])
            for r in rows:
                writer.writerow([r["id"], r["iso_date"], cents_to_str(r["amount_cents"]), r["type"], r["category"], r["description"], r["created_at"], int(r["synced"])])
        return csv_path

    def unsynced(self) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, iso_date, amount_cents, type, category, description, created_at FROM transactions WHERE synced = 0 ORDER BY id ASC")
        return [self._row_to_dict(r + (0,)) if len(r)==7 else self._row_to_dict(r) for r in cur.fetchall()]

    def mark_synced(self, tx_ids: List[int]):
        if not tx_ids:
            return
        cur = self.conn.cursor()
        cur.execute("UPDATE transactions SET synced = 1 WHERE id IN ({})".format(",".join("?"*len(tx_ids))), tx_ids)
        self.conn.commit()

# --- Config loader ---
def load_config():
    if not os.path.exists(CONFIG_PATH):
        default = {"firebase_url": "", "google_service_account_file": "", "google_sheet_name": ""}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
        return default
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# --- Cloud sync layer ---
class CloudSync:
    def __init__(self, config: dict):
        self.config = config

    # Firebase Realtime Database simple sync:
    def firebase_sync(self, db: BudgetDB) -> Dict:
        """
        Sync unsynced transactions to a Firebase Realtime Database.
        The config must include 'firebase_url' like: https://<your-db>.firebaseio.com
        We'll write each transaction under /transactions/<id>.json
        (Replace <id> with local DB id or use push if desired.)
        This uses simple unauthenticated writes or token if included as ?auth=...
        """
        base = self.config.get("firebase_url", "").rstrip("/")
        if not base:
            return {"ok": False, "message": "firebase_url not set in config.json"}

        unsynced = db.unsynced()
        if not unsynced:
            return {"ok": True, "synced": 0, "message": "No unsynced transactions"}

        synced_ids = []
        for tx in unsynced:
            # Use the local id as the key to avoid duplicates
            key = str(tx["id"])
            url = f"{base}/transactions/{key}.json"
            payload = {
                "iso_date": tx["iso_date"],
                "amount_cents": tx["amount_cents"],
                "type": tx["type"],
                "category": tx["category"],
                "description": tx["description"],
                "created_at": tx["created_at"],
                "synced_locally_at": datetime.utcnow().isoformat()
            }
            try:
                resp = requests.put(url, json=payload, timeout=10)
                if resp.status_code in (200, 201):
                    synced_ids.append(tx["id"])
                else:
                    print(f"Warning: failed to write tx {tx['id']} -> {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"Error syncing tx {tx['id']}: {e}")

        if synced_ids:
            db.mark_synced(synced_ids)
        return {"ok": True, "synced": len(synced_ids), "ids": synced_ids}

    # Google Sheets sync (optional)
    def google_sheets_sync(self, db: BudgetDB) -> Dict:
        if not GS_AVAILABLE:
            return {"ok": False, "message": "gspread/google-auth not installed"}
        sa_file = self.config.get("google_service_account_file", "").strip()
        sheet_name = self.config.get("google_sheet_name", "").strip()
        if not sa_file or not sheet_name:
            return {"ok": False, "message": "Google service account file or sheet name missing in config"}

        try:
            creds = Credentials.from_service_account_file(sa_file, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
            gc = gspread.authorize(creds)
            sh = gc.open(sheet_name)
            worksheet = None
            try:
                worksheet = sh.worksheet("transactions")
            except gspread.WorksheetNotFound:
                worksheet = sh.add_worksheet(title="transactions", rows="1000", cols="20")
                worksheet.append_row(["id", "iso_date", "amount", "type", "category", "description", "created_at", "synced"])

            unsynced = db.unsynced()
            if not unsynced:
                return {"ok": True, "synced": 0, "message": "No unsynced transactions"}

            appended_ids = []
            for tx in unsynced:
                row = [tx["id"], tx["iso_date"], cents_to_str(tx["amount_cents"]), tx["type"], tx["category"], tx["description"], tx["created_at"], 0]
                worksheet.append_row(row)
                appended_ids.append(tx["id"])

            if appended_ids:
                db.mark_synced(appended_ids)
            return {"ok": True, "synced": len(appended_ids), "ids": appended_ids}
        except Exception as e:
            return {"ok": False, "message": str(e)}

# --- CLI / Interaction ---
def prompt_add_transaction(db: BudgetDB):
    print("Add a transaction")
    raw_date = input("Date (YYYY-MM-DD, default today): ").strip()
    if not raw_date:
        iso_date = date.today().isoformat()
    else:
        try:
            iso_date = dateparser.parse(raw_date).date().isoformat()
        except Exception:
            print("Couldn't parse date; using today.")
            iso_date = date.today().isoformat()

    kind = None
    while kind not in ("expense", "income"):
        kind = input("Type: 'expense' or 'income': ").strip().lower()
    amt = input("Amount (e.g. 12.50): ").strip()
    try:
        cents = to_cents(amt)
        if kind == "expense" and cents > 0:
            cents = -cents  # expenses stored as negative amounts
    except Exception:
        print("Unable to parse amount. Aborting.")
        return

    category = input("Category (optional): ").strip()
    description = input("Description (optional): ").strip()
    txid = db.add_transaction(iso_date, cents, kind, category, description)
    print(f"Saved transaction id={txid} amount={cents_to_str(cents)} date={iso_date}")

def prompt_list(db: BudgetDB, args):
    rows = db.list_transactions(limit=args.limit)
    print(f"Last {len(rows)} transactions:")
    print("{:>4}  {:10}  {:10}  {:8}  {:12}  {}".format("ID", "Date", "Amount", "Type", "Category", "Desc"))
    for r in rows:
        print("{:>4}  {:10}  {:10}  {:8}  {:12}  {}".format(r["id"], r["iso_date"], cents_to_str(r["amount_cents"]), r["type"], (r["category"] or "")[:12], (r["description"] or "")[:30]))

def prompt_summary(db: BudgetDB, year: int, month: int):
    s = db.monthly_summary(year, month)
    inc = s.get("income", 0)
    exp = s.get("expense", 0)
    net = inc + exp  # note expense likely negative
    print(f"Summary for {year}-{month:02d}:")
    print(f"  Income:  {cents_to_str(inc)}")
    print(f"  Expense: {cents_to_str(exp)}")
    print(f"  Net:     {cents_to_str(net)}")

def prompt_export(db: BudgetDB, path: Optional[str]):
    out = db.export_csv(path or CSV_EXPORT_PATH)
    print(f"Exported CSV to {out}")

def prompt_sync(db: BudgetDB, cfg: dict):
    syncer = CloudSync(cfg)
    # Try Firebase first (simpler)
    if cfg.get("firebase_url"):
        print("Attempting Firebase sync...")
        res = syncer.firebase_sync(db)
        print(res)
    # Next try Google Sheets if configured
    elif cfg.get("google_service_account_file") and cfg.get("google_sheet_name"):
        print("Attempting Google Sheets sync...")
        res = syncer.google_sheets_sync(db)
        print(res)
    else:
        print("No cloud configured. Edit config at:", CONFIG_PATH)

def interactive_loop(db: BudgetDB, cfg: dict):
    print("Welcome to Budgeter — a simple local + optional cloud budget tracker.")
    help_text = """
Commands:
  a  add transaction
  l  list transactions
  s  monthly summary
  e  export CSV
  c  cloud sync
  q  quit
  h  help
"""
    print(help_text)
    while True:
        cmd = input("> ").strip().lower()
        if cmd in ("q", "quit", "exit"):
            print("bye.")
            break
        elif cmd in ("a", "add"):
            prompt_add_transaction(db)
        elif cmd in ("l", "list"):
            class A: pass
            args = A()
            args.limit = 50
            prompt_list(db, args)
        elif cmd in ("s", "summary"):
            raw = input("Enter year-month (e.g. 2025-08) or just year: ").strip()
            if "-" in raw:
                yr, mo = raw.split("-", 1)
                yr = int(yr); mo = int(mo)
            elif raw:
                yr = int(raw); mo = date.today().month
            else:
                yr = date.today().year; mo = date.today().month
            prompt_summary(db, yr, mo)
        elif cmd in ("e", "export"):
            prompt_export(db, None)
        elif cmd in ("c", "cloud"):
            prompt_sync(db, cfg)
        elif cmd in ("h", "help"):
            print(help_text)
        else:
            print("Unknown command. (h for help)")

# --- CLI argument entrypoint ---
def main():
    parser = argparse.ArgumentParser(description="Budgeter - local + optional cloud expense tracker")
    parser.add_argument("--add", action="store_true", help="Add a transaction (interactive)")
    parser.add_argument("--list", action="store_true", help="List last transactions")
    parser.add_argument("--export", action="store_true", help="Export CSV")
    parser.add_argument("--sync", action="store_true", help="Sync unsynced transactions to cloud (based on config)")
    parser.add_argument("--summary", nargs="?", const="", help="Monthly summary: pass YYYY-MM or YYYY")
    args = parser.parse_args()

    cfg = load_config()
    db = BudgetDB()

    if args.add:
        prompt_add_transaction(db)
        return
    if args.list:
        class A: pass
        aa = A(); aa.limit = 100
        prompt_list(db, aa)
        return
    if args.export:
        prompt_export(db, None)
        return
    if args.sync:
        prompt_sync(db, cfg)
        return
    if args.summary is not None:
        raw = args.summary
        if not raw:
            yr = date.today().year; mo = date.today().month
        elif "-" in raw:
            yr, mo = raw.split("-", 1); yr = int(yr); mo = int(mo)
        else:
            yr = int(raw); mo = date.today().month
        prompt_summary(db, yr, mo)
        return

    # default interactive REPL
    interactive_loop(db, cfg)

if __name__ == "__main__":
    main()
