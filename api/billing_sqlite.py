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
        "env": "STRIPE_PRICE_STARTER",
        "name": "Starter",
    },
    "pro": {
        "credits": 25,
        "env": "STRIPE_PRICE_PRO",
        "name": "Pro",
    },
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
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stripe_session_id TEXT UNIQUE,
                email TEXT NOT NULL,
                product_key TEXT NOT NULL,
                credits_granted INTEGER NOT NULL,
                amount_total INTEGER,
                currency TEXT,
                status TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                reason TEXT NOT NULL,
                reference_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_or_create_customer(email: str) -> Dict[str, Any]:
    email = normalize_email(email)
    if not email:
        raise ValueError("email is required")
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO customers (email, credits, created_at, updated_at) VALUES (?, 0, ?, ?)",
                (email, now, now),
            )
            row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        return dict(row)


def get_balance(email: str) -> int:
    customer = get_or_create_customer(email)
    return int(customer["credits"])


def grant_credits(
    email: str,
    credits: int,
    reason: str,
    reference_id: Optional[str] = None,
    product_key: Optional[str] = None,
    amount_total: Optional[int] = None,
    currency: Optional[str] = None,
) -> int:
    email = normalize_email(email)
    now = time.time()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO customers (email, credits, created_at, updated_at) VALUES (?, 0, ?, ?)",
                (email, now, now),
            )
            balance = 0
        else:
            balance = int(row["credits"])

        if reference_id:
            existing = conn.execute(
                "SELECT id FROM payments WHERE stripe_session_id = ?",
                (reference_id,),
            ).fetchone()
            if existing:
                return balance

        new_balance = balance + int(credits)
        conn.execute(
            "UPDATE customers SET credits = ?, updated_at = ? WHERE email = ?",
            (new_balance, now, email),
        )
        conn.execute(
            """
            INSERT INTO credit_transactions (email, delta, balance_after, reason, reference_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, int(credits), new_balance, reason, reference_id, now),
        )
        if reference_id and product_key:
            conn.execute(
                """
                INSERT INTO payments (
                    stripe_session_id, email, product_key, credits_granted,
                    amount_total, currency, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)
                """,
                (reference_id, email, product_key, int(credits), amount_total, currency, now),
            )
        return new_balance


def consume_credit(email: str, reference_id: str, amount: int = 1) -> int:
    email = normalize_email(email)
    now = time.time()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        balance = int(row["credits"]) if row else 0
        if balance < amount:
            raise ValueError("insufficient_credits")
        new_balance = balance - amount
        conn.execute(
            "UPDATE customers SET credits = ?, updated_at = ? WHERE email = ?",
            (new_balance, now, email),
        )
        conn.execute(
            """
            INSERT INTO credit_transactions (email, delta, balance_after, reason, reference_id, created_at)
            VALUES (?, ?, ?, 'ppt_conversion', ?, ?)
            """,
            (email, -amount, new_balance, reference_id, now),
        )
        return new_balance


def refund_credit(email: str, reference_id: str, amount: int = 1) -> int:
    return grant_credits(email, amount, "conversion_refund", reference_id=f"refund:{reference_id}")
