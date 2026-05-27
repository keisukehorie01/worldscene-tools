import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from billing_sqlite import DB_PATH, ensure_column, get_balances, get_conn, normalize_email
from drop2ppt_mail import mail_config_summary, send_password_reset_email, send_verification_email


VERIFY_TTL_SECONDS = int(os.getenv("AUTH_VERIFY_TTL_SECONDS", str(24 * 60 * 60)))
RESET_TTL_SECONDS = int(os.getenv("AUTH_RESET_TTL_SECONDS", str(24 * 60 * 60)))


def init_auth_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0,
                verification_token TEXT,
                verification_expires_at REAL,
                password_reset_token TEXT,
                password_reset_expires_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                last_login_at REAL
            )
            """
        )
        ensure_column(conn, "auth_users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "auth_users", "verification_token", "TEXT")
        ensure_column(conn, "auth_users", "verification_expires_at", "REAL")
        ensure_column(conn, "auth_users", "password_reset_token", "TEXT")
        ensure_column(conn, "auth_users", "password_reset_expires_at", "REAL")
        ensure_column(conn, "auth_users", "last_login_at", "REAL")
        conn.commit()


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def _get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        return _row_to_dict(conn.execute("SELECT * FROM auth_users WHERE email = ?", (normalize_email(email),)).fetchone())


def _get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        return _row_to_dict(conn.execute("SELECT * FROM auth_users WHERE id = ?", (int(user_id),)).fetchone())


def _public_user(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    balances = get_balances(user["email"])
    return {
        "id": int(user["id"]),
        "email": user["email"],
        "email_verified": bool(user.get("email_verified")),
        **balances,
    }


def current_auth_user() -> Optional[Dict[str, Any]]:
    user_id = session.get("drop2ppt_user_id")
    if not user_id:
        return None
    return _get_user_by_id(int(user_id))


def current_auth_email() -> str:
    user = current_auth_user()
    if not user or not user.get("email_verified"):
        return ""
    return normalize_email(user["email"])


def require_verified_user():
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_auth_email():
                return jsonify({"ok": False, "error": "login_required", "message": "Please log in and verify your email."}), 401
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _validate_password(password: str) -> Optional[str]:
    if len(password or "") < 8:
        return "パスワードは8文字以上で入力してください。"
    return None


def _set_session(user: Dict[str, Any]) -> None:
    sandbox_allowed = bool(session.get("drop2ppt_sandbox_allowed"))
    session.clear()
    if sandbox_allowed:
        session["drop2ppt_sandbox_allowed"] = True
    session["drop2ppt_user_id"] = int(user["id"])
    session["csrf_token"] = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute("UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE id = ?", (time.time(), time.time(), user["id"]))
        conn.commit()


def set_sandbox_auth_session(email: str, password: str) -> Optional[Dict[str, Any]]:
    email = normalize_email(email)
    if not email or not password:
        return None

    init_auth_db()
    now = time.time()
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM auth_users WHERE email = ?", (email,)).fetchone()
        if existing:
            user_id = int(existing["id"])
            conn.execute(
                """
                UPDATE auth_users
                SET email_verified = 1,
                    verification_token = NULL,
                    verification_expires_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, user_id),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO auth_users (email, password_hash, email_verified, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (email, generate_password_hash(password), now, now),
            )
            user_id = int(cur.lastrowid)
        conn.commit()

    user = _get_user_by_id(user_id)
    if user:
        _set_session(user)
    return user


def _create_verification_token(user_id: int) -> str:
    token = secrets.token_urlsafe(40)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE auth_users
            SET verification_token = ?, verification_expires_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (token, now + VERIFY_TTL_SECONDS, now, int(user_id)),
        )
        conn.commit()
    return token


def register_auth_routes(app) -> None:
    init_auth_db()

    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        return jsonify({"ok": True, "user": _public_user(current_auth_user()), "mail": mail_config_summary()})

    @app.route("/api/auth/signup", methods=["POST"])
    def auth_signup():
        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email", ""))
        password = str(payload.get("password") or "")
        password_confirm = str(payload.get("password_confirm") or "")

        if not email or "@" not in email:
            return jsonify({"ok": False, "error": "email_required", "message": "メールアドレスを入力してください。"}), 400
        password_error = _validate_password(password)
        if password_error:
            return jsonify({"ok": False, "error": "weak_password", "message": password_error}), 400
        if password != password_confirm:
            return jsonify({"ok": False, "error": "password_mismatch", "message": "確認用パスワードが一致しません。"}), 400

        now = time.time()
        with get_conn() as conn:
            existing = conn.execute("SELECT * FROM auth_users WHERE email = ?", (email,)).fetchone()
            if existing and existing["email_verified"]:
                return jsonify({"ok": False, "error": "already_registered", "message": "このメールアドレスは登録済みです。ログインしてください。"}), 409
            if existing:
                conn.execute(
                    """
                    UPDATE auth_users
                    SET password_hash = ?, updated_at = ?
                    WHERE email = ?
                    """,
                    (generate_password_hash(password), now, email),
                )
                user_id = int(existing["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO auth_users (email, password_hash, email_verified, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (email, generate_password_hash(password), now, now),
                )
                user_id = int(cur.lastrowid)
            conn.commit()

        token = _create_verification_token(user_id)
        mail_result = send_verification_email(email, token)
        user = _get_user_by_id(user_id)
        _set_session(user)
        return jsonify({
            "ok": True,
            "user": _public_user(user),
            "mail_sent": bool(mail_result.get("ok")),
            "mail_error": "" if mail_result.get("ok") else mail_result.get("error", ""),
        })

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email", ""))
        password = str(payload.get("password") or "")
        user = _get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"ok": False, "error": "login_failed", "message": "ログインに失敗しました。"}), 401
        _set_session(user)
        return jsonify({"ok": True, "user": _public_user(user)})

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.route("/api/auth/resend-verification", methods=["POST"])
    def auth_resend_verification():
        user = current_auth_user()
        if not user:
            return jsonify({"ok": False, "error": "login_required", "message": "ログインしてください。"}), 401
        if user.get("email_verified"):
            return jsonify({"ok": True, "already_verified": True})
        token = _create_verification_token(user["id"])
        mail_result = send_verification_email(user["email"], token)
        return jsonify({
            "ok": bool(mail_result.get("ok")),
            "mail_sent": bool(mail_result.get("ok")),
            "message": "認証メールを送信しました。" if mail_result.get("ok") else mail_result.get("error", "メール送信に失敗しました。"),
        }), 200 if mail_result.get("ok") else 503

    @app.route("/api/auth/verify", methods=["POST"])
    def auth_verify():
        payload = request.get_json(silent=True) or {}
        token = str(payload.get("token") or "").strip()
        if not token:
            return jsonify({"ok": False, "error": "token_required", "message": "認証トークンがありません。"}), 400
        now = time.time()
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE verification_token = ?", (token,)).fetchone()
            if not row or float(row["verification_expires_at"] or 0) < now:
                return jsonify({"ok": False, "error": "invalid_token", "message": "認証URLが無効、または有効期限が切れています。"}), 400
            conn.execute(
                """
                UPDATE auth_users
                SET email_verified = 1, verification_token = NULL,
                    verification_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, int(row["id"])),
            )
            conn.commit()
        user = _get_user_by_id(int(row["id"]))
        _set_session(user)
        return jsonify({"ok": True, "user": _public_user(user)})

    @app.route("/api/auth/forgot", methods=["POST"])
    def auth_forgot():
        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email", ""))
        if not email or "@" not in email:
            return jsonify({"ok": False, "error": "email_required", "message": "メールアドレスを入力してください。"}), 400
        user = _get_user_by_email(email)
        if user:
            token = secrets.token_urlsafe(40)
            now = time.time()
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE auth_users
                    SET password_reset_token = ?, password_reset_expires_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (token, now + RESET_TTL_SECONDS, now, int(user["id"])),
                )
                conn.commit()
            send_password_reset_email(email, token)
        return jsonify({"ok": True, "message": "アカウントが存在する場合、再設定メールを送信しました。"})

    @app.route("/api/auth/reset", methods=["POST"])
    def auth_reset():
        payload = request.get_json(silent=True) or {}
        token = str(payload.get("token") or "").strip()
        password = str(payload.get("password") or "")
        password_confirm = str(payload.get("password_confirm") or "")
        password_error = _validate_password(password)
        if password_error:
            return jsonify({"ok": False, "error": "weak_password", "message": password_error}), 400
        if password != password_confirm:
            return jsonify({"ok": False, "error": "password_mismatch", "message": "確認用パスワードが一致しません。"}), 400

        now = time.time()
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE password_reset_token = ?", (token,)).fetchone()
            if not row or float(row["password_reset_expires_at"] or 0) < now:
                return jsonify({"ok": False, "error": "invalid_token", "message": "再設定URLが無効、または有効期限が切れています。"}), 400
            conn.execute(
                """
                UPDATE auth_users
                SET password_hash = ?, password_reset_token = NULL,
                    password_reset_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (generate_password_hash(password), now, int(row["id"])),
            )
            conn.commit()
        user = _get_user_by_id(int(row["id"]))
        _set_session(user)
        return jsonify({"ok": True, "user": _public_user(user)})
