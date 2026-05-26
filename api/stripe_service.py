import os

from flask import jsonify, request

from billing_sqlite import (
    PRODUCTS,
    get_balance,
    grant_credits,
    init_billing_db,
    normalize_email,
)


try:
    import stripe
except ModuleNotFoundError:
    stripe = None


STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://worldscene.net").rstrip("/")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", f"{PUBLIC_BASE_URL}/drop2ppt").rstrip("/")


def grant_checkout_session_credits(session):
    metadata = session.get("metadata") or {}
    email = normalize_email(
        metadata.get("email")
        or session.get("customer_details", {}).get("email")
        or session.get("customer_email")
    )
    if not email:
        raise ValueError("checkout session has no email")

    product_key = metadata.get("product_key", "starter")
    product = PRODUCTS.get(product_key, PRODUCTS["starter"])
    credits = int(metadata.get("credits") or product["credits"])
    return grant_credits(
        email=email,
        credits=credits,
        reason="stripe_checkout",
        reference_id=session.get("id"),
        product_key=product_key,
        amount_total=session.get("amount_total"),
        currency=session.get("currency"),
    )


def register_stripe_routes(app):
    init_billing_db()

    @app.route("/api/billing/balance", methods=["GET"])
    def billing_balance():
        email = normalize_email(request.args.get("email", ""))
        if not email:
            return jsonify({"ok": False, "error": "email is required"}), 400
        return jsonify({"ok": True, "email": email, "credits": get_balance(email)})

    @app.route("/api/checkout/create", methods=["POST"])
    def checkout_create():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500
        if not STRIPE_SECRET_KEY:
            return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not set"}), 500

        payload = request.get_json(silent=True) or {}
        email = normalize_email(payload.get("email", ""))
        product_key = (payload.get("product") or "starter").strip()
        product = PRODUCTS.get(product_key)
        if not email:
            return jsonify({"ok": False, "error": "email is required"}), 400
        if not product:
            return jsonify({"ok": False, "error": "unknown product"}), 400

        price_id = os.getenv(product["env"], "").strip()
        if not price_id:
            return jsonify({"ok": False, "error": f"{product['env']} is not set"}), 500

        stripe.api_key = STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=email,
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{PUBLIC_APP_URL}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&email={email}",
                cancel_url=f"{PUBLIC_APP_URL}/?checkout=cancel",
                metadata={
                    "email": email,
                    "product_key": product_key,
                    "credits": str(product["credits"]),
                },
                allow_promotion_codes=True,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502
        return jsonify({"ok": True, "url": session.url})

    @app.route("/api/checkout/confirm", methods=["POST"])
    def checkout_confirm():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500
        if not STRIPE_SECRET_KEY:
            return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not set"}), 500

        payload = request.get_json(silent=True) or {}
        session_id = (payload.get("session_id") or "").strip()
        if not session_id:
            return jsonify({"ok": False, "error": "session_id is required"}), 400

        stripe.api_key = STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        if session.get("payment_status") != "paid":
            return jsonify({"ok": False, "error": "checkout session is not paid"}), 400

        try:
            balance = grant_checkout_session_credits(session)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "credits": balance})

    @app.route("/api/stripe/webhook", methods=["POST"])
    def stripe_webhook():
        if stripe is None:
            return jsonify({"ok": False, "error": "stripe package is not installed"}), 500
        if not STRIPE_SECRET_KEY:
            return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not set"}), 500

        stripe.api_key = STRIPE_SECRET_KEY
        payload = request.get_data()
        sig_header = request.headers.get("Stripe-Signature", "")

        try:
            if STRIPE_WEBHOOK_SECRET:
                event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
            else:
                event = request.get_json(force=True)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            grant_checkout_session_credits(session)

        return jsonify({"ok": True})
