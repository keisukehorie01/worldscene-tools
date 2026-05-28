import hmac
import os

from flask import jsonify, request, session

from billing_sqlite import (
    PRODUCTS,
    get_balances,
    grant_credits,
    init_billing_db,
    normalize_credit_type,
    normalize_email,
)
from drop2ppt_auth import current_auth_email, set_sandbox_auth_session


try:
    import stripe
except ModuleNotFoundError:
    stripe = None


def env_value(name, default=""):
    return os.getenv(name, default).strip()


def public_app_url():
    base_url = env_value("PUBLIC_BASE_URL", "https://worldscene.net").rstrip("/")
    return env_value("PUBLIC_APP_URL", f"{base_url}/drop2ppt").rstrip("/")


def is_test_key(key):
    return key.startswith("sk_test_") or key.startswith("rk_test_")


def requested_stripe_mode(payload):
    mode = str(payload.get("stripe_mode") or payload.get("mode") or "").strip().lower()
    if mode in {"test", "sandbox"} or payload.get("sandbox") is True:
        return "test"
    if mode in {"live", "production"}:
        return "live"

    secret_key = env_value("STRIPE_SECRET_KEY")
    return "test" if is_test_key(secret_key) else "live"


def stripe_secret_for_mode(mode):
    if mode == "test":
        return env_value("STRIPE_TEST_SECRET_KEY") or (
            env_value("STRIPE_SECRET_KEY") if is_test_key(env_value("STRIPE_SECRET_KEY")) else ""
        )
    return env_value("STRIPE_SECRET_KEY")


def webhook_secret_for_mode(mode):
    if mode == "test":
        return env_value("STRIPE_TEST_WEBHOOK_SECRET") or (
            env_value("STRIPE_WEBHOOK_SECRET") if is_test_key(stripe_secret_for_mode("test")) else ""
        )
    return env_value("STRIPE_WEBHOOK_SECRET")


def price_id_for_product(product, mode):
    if mode == "test":
        test_env = product["env"].replace("STRIPE_PRICE_", "STRIPE_TEST_PRICE_")
        return env_value(test_env) or (
            env_value(product["env"]) if is_test_key(stripe_secret_for_mode("test")) else ""
        )
    return env_value(product["env"])


def checkout_quantity(payload, product_key):
    if product_key != "high_quality":
        return 1
    try:
        quantity = int(payload.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    return max(1, min(quantity, 50))


def sandbox_checkout_allowed():
    return bool(session.get("drop2ppt_sandbox_allowed"))


def constant_time_equal(value, expected):
    return hmac.compare_digest(str(value).encode("utf-8"), str(expected).encode("utf-8"))


def grant_checkout_session_credits(session):
    metadata = session.get("metadata") or {}
    customer_details = session.get("customer_details") or {}
    email = normalize_email(
        metadata.get("email")
        or customer_details.get("email")
        or session.get("customer_email")
    )
    if not email:
        raise ValueError("checkout session has no email")

    product_key = metadata.get("product_key", "starter")
    product = PRODUCTS.get(product_key, PRODUCTS["starter"])
    credits = int(metadata.get("credits") or product["credits"])
    credit_type = normalize_credit_type(metadata.get("credit_type") or product.get("credit_type"))
    grant_credits(
        email=email,
        credits=credits,
        reason="stripe_checkout",
        reference_id=session.get("id"),
        product_key=product_key,
        credit_type=credit_type,
        amount_total=session.get("amount_total"),
        currency=session.get("currency"),
    )
    balances = get_balances(email)
    balances.update(
        {
            "product_key": product_key,
            "credit_type": credit_type,
            "credits_granted": credits,
        }
    )
    return balances


def register_stripe_routes(app):
    init_billing_db()

    @app.route("/api/sandbox/me", methods=["GET"])
    def sandbox_me():
        return jsonify({"ok": True, "sandbox_allowed": sandbox_checkout_allowed()})

    @app.route("/api/sandbox/login", methods=["POST"])
    def sandbox_login():
        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email", ""))
        password = str(payload.get("password") or "")
        configured_email = normalize_email(env_value("DROP2PPT_SANDBOX_EMAIL") or env_value("SANDBOX_CHECKOUT_EMAIL"))
        configured_password = env_value("DROP2PPT_SANDBOX_PASSWORD") or env_value("SANDBOX_CHECKOUT_PASSWORD")
        if not configured_email or not configured_password:
            return jsonify({"ok": False, "error": "sandbox login is not configured"}), 503
        if not constant_time_equal(email, configured_email) or not constant_time_equal(password, configured_password):
            return jsonify({"ok": False, "error": "sandbox login failed"}), 401
        session["drop2ppt_sandbox_allowed"] = True
        user = set_sandbox_auth_session(configured_email, configured_password)
        return jsonify({"ok": True, "sandbox_allowed": True, "user_email": user["email"] if user else configured_email})

    @app.route("/api/sandbox/logout", methods=["POST"])
    def sandbox_logout():
        session.pop("drop2ppt_sandbox_allowed", None)
        return jsonify({"ok": True, "sandbox_allowed": False})

    @app.route("/api/billing/balance", methods=["GET"])
    def billing_balance():
        email = current_auth_email()
        if not email:
            return jsonify({"ok": False, "error": "login_required", "message": "Please log in and verify your email."}), 401
        return jsonify({"ok": True, "email": email, **get_balances(email)})

    @app.route("/api/checkout/create", methods=["POST"])
    def checkout_create():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500

        payload = request.get_json(silent=True) or {}
        email = current_auth_email()
        product_key = (payload.get("product") or "starter").strip()
        product = PRODUCTS.get(product_key)
        stripe_mode = requested_stripe_mode(payload)
        stripe_secret_key = stripe_secret_for_mode(stripe_mode)
        quantity = checkout_quantity(payload, product_key)
        if not email:
            return jsonify({"ok": False, "error": "login_required", "message": "Please log in and verify your email."}), 401
        if not product:
            return jsonify({"ok": False, "error": "unknown product"}), 400
        if stripe_mode == "test" and not is_test_key(env_value("STRIPE_SECRET_KEY")):
            if not sandbox_checkout_allowed():
                return jsonify({"ok": False, "error": "sandbox checkout is not allowed for this email"}), 403
        if not stripe_secret_key:
            return jsonify({"ok": False, "error": f"Stripe {stripe_mode} secret key is not set"}), 500

        price_id = price_id_for_product(product, stripe_mode)
        if not price_id:
            return jsonify({"ok": False, "error": f"Stripe {stripe_mode} price for {product_key} is not set"}), 500

        stripe.api_key = stripe_secret_key
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=email,
                line_items=[{"price": price_id, "quantity": quantity}],
                success_url=f"{public_app_url()}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&stripe_mode={stripe_mode}&product={product_key}&quantity={quantity}",
                cancel_url=f"{public_app_url()}/?checkout=cancel&stripe_mode={stripe_mode}",
                metadata={
                    "email": email,
                    "product_key": product_key,
                    "quantity": str(quantity),
                    "unit_credits": str(product["credits"]),
                    "credits": str(product["credits"] * quantity),
                    "credit_type": product.get("credit_type", "standard"),
                    "stripe_mode": stripe_mode,
                },
                allow_promotion_codes=True,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, "url": session.url, "stripe_mode": stripe_mode, "quantity": quantity})

    @app.route("/api/checkout/confirm", methods=["POST"])
    def checkout_confirm():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500

        payload = request.get_json(silent=True) or {}
        session_id = (payload.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"ok": False, "error": "session_id is required"}), 400

        stripe_mode = "test" if session_id.startswith("cs_test_") else "live"
        stripe_secret_key = stripe_secret_for_mode(stripe_mode)
        if not stripe_secret_key:
            return jsonify({"ok": False, "error": f"Stripe {stripe_mode} secret key is not set"}), 500

        stripe.api_key = stripe_secret_key
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        if session.get("payment_status") != "paid":
            return jsonify({"ok": False, "error": "checkout session is not paid"}), 400

        try:
            session_email = normalize_email(
                (session.get("metadata") or {}).get("email")
                or (session.get("customer_details") or {}).get("email")
                or session.get("customer_email")
            )
            auth_email = current_auth_email()
            if auth_email and session_email and auth_email != session_email:
                return jsonify({"ok": False, "error": "email_mismatch"}), 403
            balances = grant_checkout_session_credits(session)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, **balances})

    @app.route("/api/stripe/webhook", methods=["POST"])
    def stripe_webhook():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500

        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature", "")

        try:
            webhook_secrets = [secret for secret in (webhook_secret_for_mode("live"), webhook_secret_for_mode("test")) if secret]
            if webhook_secrets and sig_header:
                last_error = None
                event = None
                for secret in webhook_secrets:
                    try:
                        event = stripe.Webhook.construct_event(payload, sig_header, secret)
                        break
                    except Exception as exc:
                        last_error = exc
                if event is None:
                    raise last_error or ValueError("webhook verification failed")
            else:
                event = request.get_json(force=True)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            grant_checkout_session_credits(session)

        return jsonify({"ok": True})
