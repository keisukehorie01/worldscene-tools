import html
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return default


def mail_config_summary() -> dict:
    username = _env_first("MAIL_USERNAME", "SMTP_USER")
    return {
        "server": _env_first("MAIL_SERVER", "SMTP_HOST") or "-",
        "port": int(_env_first("MAIL_PORT", "SMTP_PORT", default="465") or 465),
        "use_ssl": _env_bool("MAIL_USE_SSL", True),
        "use_tls": _env_bool("MAIL_USE_TLS", False),
        "username": username or "-",
        "sender": _env_first("MAIL_DEFAULT_SENDER", "SMTP_FROM", default=username) or "-",
        "password_set": bool(os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD")),
    }


def _mail_settings() -> dict:
    username = _env_first("MAIL_USERNAME", "SMTP_USER")
    return {
        "server": _env_first("MAIL_SERVER", "SMTP_HOST"),
        "port": int(_env_first("MAIL_PORT", "SMTP_PORT", default="465") or 465),
        "use_ssl": _env_bool("MAIL_USE_SSL", True),
        "use_tls": _env_bool("MAIL_USE_TLS", False),
        "username": username,
        "auth_username": _env_first("MAIL_AUTH_USERNAME", default=username),
        "password": os.environ.get("MAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "",
        "sender_address": _env_first("MAIL_DEFAULT_SENDER", "SMTP_FROM", default=username),
        "sender_name": _env_first("MAIL_FROM_NAME", "SMTP_FROM_NAME", default="Drop2PPT"),
    }


def _app_url(path: str = "") -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "https://worldscene.net/drop2ppt").rstrip("/")
    return f"{base}/{path.lstrip('/')}" if path else base


def _html_email(title: str, body_text: str, cta_url: str, cta_label: str) -> str:
    safe_title = html.escape(title)
    safe_body = "<br>\n".join(html.escape(line) for line in body_text.splitlines())
    safe_url = html.escape(cta_url)
    safe_label = html.escape(cta_label)
    return f"""<!doctype html>
<html lang="ja">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#eef6f7;color:#0b2436;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Yu Gothic',sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 12px;">
    <div style="background:#fff;border:1px solid #d7e8ea;border-radius:14px;overflow:hidden;box-shadow:0 18px 50px rgba(6,60,65,.12);">
      <div style="background:#0b3a46;color:#fff;padding:24px;">
        <div style="font-size:13px;font-weight:800;letter-spacing:.1em;color:#78f0e3;">WorldScene Drop2PPT</div>
        <h1 style="margin:10px 0 0;font-size:25px;line-height:1.35;">{safe_title}</h1>
      </div>
      <div style="padding:24px;font-size:15px;line-height:1.9;">
        <p style="margin:0 0 22px;">{safe_body}</p>
        <p style="margin:0 0 18px;">
          <a href="{safe_url}" style="display:inline-block;background:#0f9b8e;color:#fff;text-decoration:none;font-weight:800;padding:13px 20px;border-radius:10px;">{safe_label}</a>
        </p>
        <p style="margin:18px 0 0;color:#607986;font-size:12px;line-height:1.7;">ボタンが開けない場合はこちら:<br><a href="{safe_url}" style="color:#0f766e;word-break:break-all;">{safe_url}</a></p>
      </div>
    </div>
  </div>
</body>
</html>"""


def send_email(to: str, subject: str, body_text: str, cta_url: str = "", cta_label: str = "") -> dict:
    settings = _mail_settings()
    sender = formataddr((settings["sender_name"], settings["sender_address"])) if settings["sender_address"] else ""
    if not settings["server"] or not settings["auth_username"] or not settings["password"] or not sender:
        return {"ok": False, "error": "SMTP設定が不足しています。"}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(body_text)
    if cta_url:
        message.add_alternative(_html_email(subject, body_text, cta_url, cta_label or "開く"), subtype="html")

    try:
        if settings["use_ssl"]:
            with smtplib.SMTP_SSL(settings["server"], settings["port"], timeout=15) as smtp:
                smtp.ehlo()
                smtp.login(settings["auth_username"], settings["password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings["server"], settings["port"], timeout=15) as smtp:
                smtp.ehlo()
                if settings["use_tls"]:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(settings["auth_username"], settings["password"])
                smtp.send_message(message)
        return {"ok": True, "error": ""}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "SMTP認証に失敗しました。"}
    except Exception as exc:
        return {"ok": False, "error": f"メール送信に失敗しました: {exc.__class__.__name__}"}


def send_verification_email(email: str, token: str) -> dict:
    url = _app_url(f"auth.html?verify_token={token}")
    body = (
        "Drop2PPTのメール認証を行います。\n\n"
        "以下のURLを開いて、メールアドレスを確認してください。\n"
        "このURLの有効期限は24時間です。\n\n"
        f"{url}\n\n"
        "このメールに心当たりがない場合は破棄してください。"
    )
    return send_email(email, "Drop2PPT メール認証", body, url, "メールを認証する")


def send_password_reset_email(email: str, token: str) -> dict:
    url = _app_url(f"auth.html?reset_token={token}")
    body = (
        "Drop2PPTのパスワード再設定を受け付けました。\n\n"
        "以下のURLから新しいパスワードを設定してください。\n"
        "このURLの有効期限は24時間です。\n\n"
        f"{url}\n\n"
        "このメールに心当たりがない場合は破棄してください。"
    )
    return send_email(email, "Drop2PPT パスワード再設定", body, url, "パスワードを再設定する")
