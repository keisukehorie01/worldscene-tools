import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("BILLING_DB_PATH", BASE_DIR / "runtime" / "billing.sqlite3"))

PRODUCTS = {
    "starter": {
        "credits": 5,
        "credit_type": "standard",
        "env": "STRIPE_PRICE_STARTER",
        "name": "Starter",
    },
    "pro": {
        "credits": 25,
        "credit_type": "standard",
        "env": "STRIPE_PRICE_PRO",
        "name": "Pro",
    },
    "high_quality": {
        "credits": 1,
        "credit_type": "high_quality",
        "env": "STRIPE_PRICE_HIGH_QUALITY",
        "name": "High Quality",
    },
}

CREDIT_COLUMNS = {
    "standard": "standard_credits",
    "high_quality": "high_quality_credits",
}


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_billing_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                email TEXT PRIMARY KEY,
                credits INTEGER NOT NULL DEFAULT 0,
                standard_credits INTEGER NOT NULL DEFAULT 0,
                high_quality_credits INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        ensure_column(conn, "customers", "standard_credits", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "customers", "high_quality_credits", "INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            UPDATE customers
            SET standard_credits = credits
            WHERE standard_credits = 0 AND credits > 0
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stripe_session_id TEXT UNIQUE,
                email TEXT NOT NULL,
                product_key TEXT NOT NULL,
                credit_type TEXT NOT NULL DEFAULT 'standard',
                credits_granted INTEGER NOT NULL,
                amount_total INTEGER,
                currency TEXT,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        ensure_column(conn, "payments", "credit_type", "TEXT NOT NULL DEFAULT 'standard'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                credit_type TEXT NOT NULL DEFAULT 'standard',
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                reference_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        ensure_column(conn, "credit_transactions", "credit_type", "TEXT NOT NULL DEFAULT 'standard'")


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_credit_type(credit_type: Optional[str]) -> str:
    credit_type = (credit_type or "standard").strip().lower()
    if credit_type in CREDIT_COLUMNS:
        return credit_type
    return "standard"


def get_or_create_customer(email: str) -> Dict[str, Any]:
    email = normalize_email(email)
    if not email:
        raise ValueError("email is required")
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO customers (
                    email, credits, standard_credits, high_quality_credits, created_at, updated_at
                ) VALUES (?, 0, 0, 0, ?, ?)
                """,
                (email, now, now),
            )
            row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        return dict(row)


def get_balance(email: str) -> int:
    balances = get_balances(email)
    return int(balances["credits"])


def get_balances(email: str) -> Dict[str, int]:
    customer = get_or_create_customer(email)
    standard = int(customer.get("standard_credits") or customer.get("credits") or 0)
    high_quality = int(customer.get("high_quality_credits") or 0)
    return {
        "credits": standard + high_quality,
        "standard_credits": standard,
        "high_quality_credits": high_quality,
    }


def grant_credits(
    email: str,
    credits: int,
    reason: str,
    reference_id: Optional[str] = None,
    product_key: Optional[str] = None,
    credit_type: Optional[str] = None,
    amount_total: Optional[int] = None,
    currency: Optional[str] = None,
) -> int:
    email = normalize_email(email)
    credit_type = normalize_credit_type(credit_type)
    column = CREDIT_COLUMNS[credit_type]
    now = time.time()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO customers (
                    email, credits, standard_credits, high_quality_credits, created_at, updated_at
                ) VALUES (?, 0, 0, 0, ?, ?)
                """,
                (email, now, now),
            )
            balance = 0
        else:
            balance = int(row[column])

        if reference_id:
            existing = conn.execute(
                "SELECT id FROM payments WHERE stripe_session_id = ?",
                (reference_id,),
            ).fetchone()
            if existing:
                return balance

        new_balance = balance + int(credits)
        conn.execute(
            f"UPDATE customers SET {column} = ?, updated_at = ? WHERE email = ?",
            (new_balance, now, email),
        )
        if credit_type == "standard":
            conn.execute(
                "UPDATE customers SET credits = ? WHERE email = ?",
                (new_balance, email),
            )
        conn.execute(
            """
            INSERT INTO credit_transactions (
                email, credit_type, delta, balance_after, reason, reference_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email, credit_type, int(credits), new_balance, reason, reference_id, now),
        )
        if reference_id and product_key:
            conn.execute(
                """
                INSERT INTO payments (
                    stripe_session_id, email, product_key, credit_type, credits_granted,
                    amount_total, currency, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)
                """,
                (reference_id, email, product_key, credit_type, int(credits), amount_total, currency, now),
            )
        return new_balance


def consume_credit(email: str, reference_id: str, amount: int = 1, credit_type: Optional[str] = None) -> int:
    email = normalize_email(email)
    credit_type = normalize_credit_type(credit_type)
    column = CREDIT_COLUMNS[credit_type]
    now = time.time()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        balance = int(row[column]) if row else 0
        if balance < amount:
            raise ValueError("insufficient_credits")
        new_balance = balance - amount
        conn.execute(
            f"UPDATE customers SET {column} = ?, updated_at = ? WHERE email = ?",
            (new_balance, now, email),
        )
        if credit_type == "standard":
            conn.execute(
                "UPDATE customers SET credits = ? WHERE email = ?",
                (new_balance, email),
            )
        conn.execute(
            """
            INSERT INTO credit_transactions (
                email, credit_type, delta, balance_after, reason, reference_id, created_at
            )
            VALUES (?, ?, ?, ?, 'ppt_conversion', ?, ?)
            """,
            (email, credit_type, -amount, new_balance, reference_id, now),
        )
        return new_balance


def refund_credit(email: str, reference_id: str, amount: int = 1, credit_type: Optional[str] = None) -> int:
    return grant_credits(
        email,
        amount,
        "conversion_refund",
        reference_id=f"refund:{reference_id}",
        credit_type=credit_type,
    )
