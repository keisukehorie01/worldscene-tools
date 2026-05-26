import os
import json
import uuid
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ModuleNotFoundError:
    service_account = None
    build = None
    HttpError = Exception

from db import get_db_connection
from billing_config import (
    PRODUCT_POINTS,
    FREE_REGISTRATION_POINTS,
    ANALYZE_POINT_COST,
)
from billing_sqlite import DB_PATH, get_conn, init_billing_db
from ppt_service import (
    MALWARE_SCAN_ENABLED,
    MALWARE_SCAN_REQUIRED,
    malware_scan_command,
    register_ppt_routes,
)
from stripe_service import register_stripe_routes

load_dotenv()

app = Flask(__name__)
register_ppt_routes(app)
register_stripe_routes(app)

GOOGLE_PLAY_PACKAGE_NAME = os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "").strip()
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
APP_AUTH_TOKEN = os.getenv("APP_AUTH_TOKEN", "").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

ANDROID_PUBLISHER_SCOPE = ["https://www.googleapis.com/auth/androidpublisher"]

PREFERRED_PRIMARY_TYPES = {
    "tourist_attraction": 40,
    "historical_landmark": 38,
    "cultural_landmark": 36,
    "buddhist_temple": 35,
    "hindu_temple": 35,
    "church": 34,
    "mosque": 34,
    "synagogue": 34,
    "museum": 32,
    "zoo": 30,
    "park": 20,
    "library": 15,
    "amusement_park": 18,
}

DISFAVORED_NAME_KEYWORDS = {
    "parking": -20,
    "station": -10,
    "bus stop": -12,
    "ticket": -8,
    "gate": -6,
}

NOISY_NAME_KEYWORDS = {
    "playground": -18,
    "children's playground": -18,
    "児童遊園": -18,
    "遊園": -12,
    "草地": -16,
}


def build_android_publisher():
    if service_account is None or build is None:
        raise RuntimeError("Google API client libraries are not installed")

    if not GOOGLE_APPLICATION_CREDENTIALS:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set")

    if not os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        raise RuntimeError(
            f"Service account JSON not found: {GOOGLE_APPLICATION_CREDENTIALS}"
        )

    print(f"SC_BILLING sa_file={GOOGLE_APPLICATION_CREDENTIALS}")

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS,
        scopes=ANDROID_PUBLISHER_SCOPE,
    )

    print(f"SC_BILLING service_account_email={credentials.service_account_email}")

    return build(
        "androidpublisher",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def verify_google_play_product_purchase(
    package_name: str,
    product_id: str,
    purchase_token: str,
) -> Dict[str, Any]:
    service = build_android_publisher()

    response = (
        service.purchases()
        .products()
        .get(
            packageName=package_name,
            productId=product_id,
            token=purchase_token,
        )
        .execute()
    )

    return response


def acknowledge_google_play_product_purchase(
    package_name: str,
    product_id: str,
    purchase_token: str,
) -> None:
    service = build_android_publisher()

    (
        service.purchases()
        .products()
        .acknowledge(
            packageName=package_name,
            productId=product_id,
            token=purchase_token,
            body={},
        )
        .execute()
    )


def get_or_create_user(conn, app_user_id: str) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM users
            WHERE app_user_id = %s
            LIMIT 1
            """,
            (app_user_id,)
        )
        user = cur.fetchone()

        if user:
            return user

        user_uuid = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO users (
                user_uuid,
                platform,
                app_user_id,
                points_balance,
                status
            ) VALUES (%s, 'android', %s, %s, 'active')
            """,
            (user_uuid, app_user_id, FREE_REGISTRATION_POINTS)
        )

        user_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO point_transactions (
                user_id,
                transaction_type,
                points_delta,
                balance_after,
                related_purchase_id,
                source_type,
                source_id,
                note
            ) VALUES (
                %s, 'grant', %s, %s, NULL, 'registration', NULL, %s
            )
            """,
            (
                user_id,
                FREE_REGISTRATION_POINTS,
                FREE_REGISTRATION_POINTS,
                f"Welcome bonus: {FREE_REGISTRATION_POINTS} points"
            )
        )

        cur.execute(
            """
            SELECT * FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )
        return cur.fetchone()


def get_user_by_app_user_id(conn, app_user_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM users
            WHERE app_user_id = %s
            LIMIT 1
            """,
            (app_user_id,)
        )
        return cur.fetchone()


def require_app_token() -> bool:
    if not APP_AUTH_TOKEN:
        return True

    received = request.headers.get("X-App-Token", "").strip()
    return received == APP_AUTH_TOKEN


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def normalize_language_code(language: str) -> str:
    lang = (language or "").strip()
    if not lang:
        return "ja"

    lowered = lang.lower()

    if lowered in {"zh-tw", "zh-hk", "zh-hant", "zh-hant-tw"}:
        return "zh-TW"
    if lowered in {"zh-cn", "zh-hans", "zh-hans-cn", "zh"}:
        return "zh-CN"
    if lowered == "es-419":
        return "es-419"
    if lowered == "pt-br":
        return "pt-BR"
    if lowered == "fil":
        return "fil"

    return lang


def normalize_place_name(name: str) -> str:
    if not name:
        return ""

    s = unicodedata.normalize("NFKC", name).lower().strip()

    replacements = [
        " temple",
        " shrine",
        " museum",
        " park",
        " zoo",
        " tourist attraction",
        "the ",
    ]
    for rep in replacements:
        s = s.replace(rep, "")

    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def distance_score(distance_meters: Optional[float]) -> float:
    if distance_meters is None:
        return 0
    if distance_meters <= 15:
        return 40
    if distance_meters <= 50:
        return 34
    if distance_meters <= 100:
        return 28
    if distance_meters <= 200:
        return 20
    if distance_meters <= 400:
        return 12
    if distance_meters <= 700:
        return 6
    return 0


def candidate_score(place: Dict[str, Any]) -> float:
    score = 0.0

    score += distance_score(place.get("distance_meters"))
    score += PREFERRED_PRIMARY_TYPES.get(place.get("primary_type"), 0)

    name = (place.get("name") or "").lower()
    for keyword, penalty in DISFAVORED_NAME_KEYWORDS.items():
        if keyword in name:
            score += penalty

    for keyword, penalty in NOISY_NAME_KEYWORDS.items():
        if keyword in name:
            score += penalty

    if place.get("address"):
        score += 3
    if place.get("name"):
        score += 3
    if place.get("lat") is not None and place.get("lng") is not None:
        score += 2

    return round(score, 1)


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Any, Dict[str, Any]] = {}

    for c in candidates:
        key = (
            normalize_place_name(c.get("name", "")),
            c.get("primary_type"),
            round(float(c.get("lat") or 0), 4),
            round(float(c.get("lng") or 0), 4),
        )

        current = grouped.get(key)
        if current is None:
            grouped[key] = c
            continue

        current_score = float(current.get("score") or 0)
        new_score = float(c.get("score") or 0)

        if new_score > current_score:
            grouped[key] = c
        elif new_score == current_score:
            current_distance = current.get("distance_meters")
            new_distance = c.get("distance_meters")
            current_distance = current_distance if current_distance is not None else 99999999
            new_distance = new_distance if new_distance is not None else 99999999
            if new_distance < current_distance:
                grouped[key] = c

    return list(grouped.values())


def should_auto_select(candidates: List[Dict[str, Any]]) -> bool:
    if not candidates:
        return False
    if len(candidates) == 1:
        return True

    first = candidates[0]
    second = candidates[1]

    first_score = float(first.get("score") or 0)
    second_score = float(second.get("score") or 0)

    return first_score >= 65 and (first_score - second_score) >= 12


def search_places_nearby(
    lat: float,
    lng: float,
    radius: float,
    language: str = "ja"
) -> List[Dict[str, Any]]:
    if not GOOGLE_PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")

    url = "https://places.googleapis.com/v1/places:searchNearby"
    language_code = normalize_language_code(language)

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": ",".join([
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.primaryType",
            "places.types",
        ]),
    }

    body = {
        "includedTypes": [
            "tourist_attraction",
            "museum",
            "historical_landmark",
            "cultural_landmark",
            "park",
            "zoo",
            "amusement_park",
            "library",
            "church",
            "mosque",
            "synagogue",
            "hindu_temple",
            "buddhist_temple"
        ],
        "maxResultCount": 15,
        "languageCode": language_code,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": radius
            }
        },
        "rankPreference": "DISTANCE"
    }

    resp = requests.post(url, headers=headers, json=body, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    places = data.get("places", [])
    results = []

    for p in places:
        loc = p.get("location", {}) or {}
        plat = loc.get("latitude")
        plng = loc.get("longitude")

        distance = None
        if plat is not None and plng is not None:
            distance = haversine_meters(lat, lng, plat, plng)

        results.append({
            "place_id": p.get("id", ""),
            "name": ((p.get("displayName") or {}).get("text")) or "",
            "address": p.get("formattedAddress"),
            "lat": plat,
            "lng": plng,
            "primary_type": p.get("primaryType"),
            "types": p.get("types", []),
            "distance_meters": round(distance, 1) if distance is not None else None,
        })

    return results


def enrich_and_rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for c in candidates:
        c["score"] = candidate_score(c)
        enriched.append(c)

    enriched = dedupe_candidates(enriched)

    enriched.sort(
        key=lambda x: (
            -(float(x.get("score") or 0)),
            x.get("distance_meters") if x.get("distance_meters") is not None else 99999999
        )
    )
    return enriched


def resolve_analyze_cost(category: str, mode: str) -> int:
    category_lower = (category or "").strip().lower()
    mode_lower = (mode or "").strip().lower()

    if category_lower == "tourist":
        return ANALYZE_POINT_COST.get("tourist", 20)

    if mode_lower in {"tourist", "history_deep"}:
        return ANALYZE_POINT_COST.get("tourist", 20)

    if category_lower == "book":
        return ANALYZE_POINT_COST.get("book", 10)

    if mode_lower == "book":
        return ANALYZE_POINT_COST.get("book", 10)

    if mode_lower == "basic":
        return ANALYZE_POINT_COST.get("basic", 10)

    return ANALYZE_POINT_COST.get("other", 10)


def build_analysis_prompt(category: str, mode: str, language: str, place_name: str) -> str:
    output_language = language or "ja"
    category_lower = (category or "").lower()
    mode_lower = (mode or "").lower()

    if category_lower in ["book", "manga", "printed_page"]:
        return f"""
You are an image scene description assistant.

Output language: {output_language}

Category: Book / Manga / Printed Page

Core rules:
1. This category is DESCRIPTION FIRST.
2. Do NOT translate dialogue line-by-line.
3. Do NOT rewrite dialogue line-by-line.
4. Do NOT output full dialogue transcripts.
5. Keep the explanation grounded in the visible page.
6. Describe what is visually happening:
   - characters
   - actions
   - facial expressions
   - relationships
   - mood
   - scene composition
7. If text exists, describe its role briefly when useful.
8. If the manga / book title is clearly recognizable from the page, you may state it.
9. If a character is clearly recognizable or explicitly named on the page, you may state the character name.
10. If you are highly confident from well-known visual identity, you may mention the likely title or likely character name, but clearly mark it as likely.
11. Do not invent uncertain names. If uncertain, say "unknown character" or "likely <name>".
12. All output must be in the target language.
13. Do NOT output JSON.
14. Keep the structure exactly as follows:

title_and_characters:
<State the likely or confirmed work title and character names if recognizable. If not, say unknown.>

page_description:
<one paragraph>

panel_descriptions:
1. <panel 1 description>
2. <panel 2 description>
3. <panel 3 description>

short_description:
<short summary>
""".strip()

    if mode_lower == "history_deep":
        return f"""
You are a historical and tourism analysis assistant.

Output language: {output_language}
Known place name: {place_name or "unknown"}

Analyze the image carefully and provide the result with the following headings exactly:

place_identification:
Identify the most likely place or explain uncertainty.

detailed_overview:
Describe what is visually present in detail.

historical_cultural_context:
Explain the historical or cultural meaning, especially why this place matters.

surroundings_and_features:
Explain visible structures, environment, style, or atmosphere.

traveler_notes:
Give useful and concise visitor-oriented notes.

important_rule:
Do not output JSON.
""".strip()

    if mode_lower == "tourist":
        return f"""
You are a tourism scene analysis assistant.

Output language: {output_language}
Known place name: {place_name or "unknown"}

Provide the result using exactly these headings:

place_identification:
overview:
visible_features:
mood_and_atmosphere:
notes:

Do not output JSON.
""".strip()

    return f"""
You are an image scene analysis assistant.

Output language: {output_language}
Known place name: {place_name or "unknown"}

Provide a grounded explanation with these headings exactly:

overview:
visible_features:
mood:
notes:

Do not output JSON.
""".strip()


def call_gemini_analyze(prompt: str, image_base64: str, mime_type: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }
        ]
    }

    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No Gemini candidates returned")

    first = candidates[0]
    finish_reason = first.get("finishReason")
    if finish_reason and finish_reason not in ["STOP", "MAX_TOKENS"]:
        raise RuntimeError(f"Gemini finishReason={finish_reason}")

    parts = ((first.get("content") or {}).get("parts")) or []
    text = "".join(part.get("text", "") for part in parts if part.get("text"))

    if not text.strip():
        raise RuntimeError("Gemini returned empty text")

    return text.strip()


def consume_points(
    conn,
    user: Dict[str, Any],
    points_needed: int,
    note: str,
    source_type: str = "analyze",
    source_id: Optional[str] = None,
) -> int:
    current_balance = int(user["points_balance"])

    if current_balance < points_needed:
        raise ValueError("insufficient_points")

    new_balance = current_balance - points_needed

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET points_balance = %s
            WHERE id = %s
            """,
            (new_balance, user["id"])
        )

        cur.execute(
            """
            INSERT INTO point_transactions (
                user_id,
                transaction_type,
                points_delta,
                balance_after,
                related_purchase_id,
                source_type,
                source_id,
                note
            ) VALUES (
                %s, 'consume', %s, %s, NULL, %s, %s, %s
            )
            """,
            (
                user["id"],
                -points_needed,
                new_balance,
                source_type,
                source_id,
                note
            )
        )

    user["points_balance"] = new_balance
    return new_balance


@app.route("/api/health", methods=["GET"])
def health():
    try:
        init_billing_db()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    1 AS ok,
                    COUNT(*) AS customer_count,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now') AS server_time
                FROM customers
                """
            ).fetchone()

        scan_command = malware_scan_command(DB_PATH)
        scanner_available = (not MALWARE_SCAN_ENABLED) or bool(scan_command)
        healthy = scanner_available or not MALWARE_SCAN_REQUIRED

        return jsonify({
            "success": healthy,
            "message": "Drop2PPT API health OK" if healthy else "Malware scanner is required but unavailable",
            "data": {
                "ok": bool(row["ok"]),
                "storage": "sqlite",
                "db_path": str(DB_PATH),
                "customer_count": row["customer_count"],
                "server_time": row["server_time"],
                "malware_scan_enabled": MALWARE_SCAN_ENABLED,
                "malware_scan_required": MALWARE_SCAN_REQUIRED,
                "malware_scanner_available": bool(scan_command),
                "malware_scanner_command": scan_command[0] if scan_command else None,
            }
        }), 200 if healthy else 503

    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Health check failed",
            "error": str(e)
        }), 500


@app.route("/api/points/balance", methods=["POST"])
def points_balance():
    try:
        if not require_app_token():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        app_user_id = str(data.get("app_user_id", "")).strip()

        if not app_user_id:
            return jsonify({"ok": False, "error": "app_user_id required"}), 400

        conn = get_db_connection()
        try:
            user = get_or_create_user(conn, app_user_id)
            conn.commit()
            return jsonify({
                "ok": True,
                "app_user_id": app_user_id,
                "points_balance": int(user["points_balance"]),
            }), 200
        finally:
            conn.close()

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "points_balance_failed",
            "message": str(e),
        }), 500
@app.route("/api/place/resolve", methods=["POST"])
def place_resolve():
    try:
        if not require_app_token():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}

        lat = data.get("lat")
        lng = data.get("lng")
        radius = data.get("radius", 500)
        top_n = data.get("top_n", 3)
        language = str(data.get("language", "")).strip() or "ja"

        if lat is None or lng is None:
            return jsonify({"ok": False, "error": "lat/lng required"}), 400

        try:
            lat = float(lat)
            lng = float(lng)
            radius = float(radius)
            top_n = int(top_n)
        except Exception:
            return jsonify({"ok": False, "error": "lat/lng/radius/top_n must be numeric"}), 400

        if top_n < 1:
            top_n = 1
        if top_n > 5:
            top_n = 5

        candidates = search_places_nearby(
            lat=lat,
            lng=lng,
            radius=radius,
            language=language
        )
        ranked = enrich_and_rank_candidates(candidates)
        top_candidates = ranked[:top_n]

        selected_candidate = top_candidates[0] if should_auto_select(top_candidates) else None

        return jsonify({
            "ok": True,
            "selected_candidate": selected_candidate,
            "top_candidates": top_candidates,
            "has_more": len(ranked) > top_n,
            "all_count": len(ranked),
            "debug": {
                "lat": lat,
                "lng": lng,
                "radius": radius,
                "top_n": top_n,
                "language": language,
                "raw_count": len(candidates),
                "ranked_count": len(ranked),
            }
        }), 200

    except requests.HTTPError as e:
        response_text = ""
        status_code = 502
        try:
            status_code = e.response.status_code
            response_text = e.response.text
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "error": "places_api_failed",
            "details": response_text
        }), 502 if status_code < 500 else 503

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        if not require_app_token():
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}

        app_user_id = str(data.get("app_user_id", "")).strip()
        category = str(data.get("category", "")).strip()
        mode = str(data.get("mode", "")).strip()
        language = str(data.get("language", "")).strip()
        image_base64 = str(data.get("image_base64", "")).strip()
        mime_type = str(data.get("mime_type", "")).strip() or "image/jpeg"
        place_name = str(data.get("place_name", "")).strip()

        if not app_user_id:
            return jsonify({"ok": False, "error": "app_user_id required"}), 400

        if not image_base64:
            return jsonify({"ok": False, "error": "image_base64 required"}), 400

        points_needed = resolve_analyze_cost(category, mode)

        conn = get_db_connection()
        try:
            user = get_or_create_user(conn, app_user_id)

            current_balance = int(user["points_balance"])
            if current_balance < points_needed:
                return jsonify({
                    "ok": False,
                    "error": "insufficient_points",
                    "required_points": points_needed,
                    "points_balance": current_balance
                }), 402

            prompt = build_analysis_prompt(
                category=category,
                mode=mode,
                language=language,
                place_name=place_name,
            )

            result_text = call_gemini_analyze(
                prompt=prompt,
                image_base64=image_base64,
                mime_type=mime_type,
            )

            new_balance = current_balance
            if points_needed > 0:
                new_balance = consume_points(
                    conn=conn,
                    user=user,
                    points_needed=points_needed,
                    note=f"Analyze mode={mode}, category={category}, place={place_name or 'none'}",
                    source_type="analyze",
                    source_id=None,
                )

            conn.commit()

            return jsonify({
                "ok": True,
                "text": result_text,
                "points_consumed": points_needed,
                "points_balance": new_balance,
                "debug": {
                    "category": category,
                    "mode": mode,
                    "language": language,
                    "place_name": place_name,
                    "gemini_model": GEMINI_MODEL,
                }
            }), 200

        except ValueError as e:
            conn.rollback()
            if str(e) == "insufficient_points":
                return jsonify({
                    "ok": False,
                    "error": "insufficient_points"
                }), 402
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except requests.HTTPError as e:
        response_text = ""
        status_code = 502
        try:
            status_code = e.response.status_code
            response_text = e.response.text
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "error": "gemini_api_failed",
            "details": response_text
        }), 502 if status_code < 500 else 503

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/api/billing/verify", methods=["POST"])
def billing_verify():
    try:
        if not require_app_token():
            return jsonify({"success": False, "message": "unauthorized"}), 401

        data = request.get_json(silent=True) or {}

        app_user_id = str(data.get("app_user_id", "")).strip()
        product_id = str(data.get("product_id", "")).strip()
        purchase_token = str(data.get("purchase_token", "")).strip()
        package_name = str(data.get("package_name", "")).strip() or GOOGLE_PLAY_PACKAGE_NAME

        print(f"SC_BILLING verify app_user_id={app_user_id}")
        print(f"SC_BILLING verify package_name={package_name}")
        print(f"SC_BILLING verify env_package_name={GOOGLE_PLAY_PACKAGE_NAME}")
        print(f"SC_BILLING verify product_id={product_id}")
        print(f"SC_BILLING verify token_prefix={purchase_token[:20] if purchase_token else ''}")

        if not app_user_id:
            return jsonify({"success": False, "message": "app_user_id is required"}), 400

        if not product_id:
            return jsonify({"success": False, "message": "product_id is required"}), 400

        if not purchase_token:
            return jsonify({"success": False, "message": "purchase_token is required"}), 400

        if not package_name:
            return jsonify({"success": False, "message": "package_name is required"}), 400

        if product_id not in PRODUCT_POINTS:
            return jsonify({
                "success": False,
                "message": f"unknown product_id: {product_id}"
            }), 400

        if package_name != GOOGLE_PLAY_PACKAGE_NAME:
            return jsonify({
                "success": False,
                "message": "package_name mismatch"
            }), 400

        points_to_grant = PRODUCT_POINTS[product_id]

        try:
            play_response = verify_google_play_product_purchase(
                package_name=package_name,
                product_id=product_id,
                purchase_token=purchase_token,
            )
            print(f"SC_BILLING google verify ok product_id={product_id} orderId={play_response.get('orderId')}")
        except HttpError as e:
            status_code = getattr(e, "status_code", None) or getattr(e.resp, "status", 500)
            print(f"SC_BILLING google verify failed status={status_code} error={str(e)}")
            return jsonify({
                "success": False,
                "message": "Google Play verification failed",
                "error": str(e),
                "google_http_status": status_code,
            }), 400 if int(status_code) < 500 else 502

        purchase_state = int(play_response.get("purchaseState", -1))
        acknowledgement_state = int(play_response.get("acknowledgementState", -1))
        order_id = play_response.get("orderId")

        print(
            "SC_BILLING google response "
            f"purchase_state={purchase_state} "
            f"ack_state={acknowledgement_state} "
            f"order_id={order_id}"
        )

        if purchase_state != 0:
            return jsonify({
                "success": False,
                "message": "Purchase is not completed",
                "data": {
                    "purchase_state": purchase_state,
                    "acknowledgement_state": acknowledgement_state,
                    "google_response": play_response,
                }
            }), 400

        conn = get_db_connection()
        try:
            user = get_or_create_user(conn, app_user_id)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM purchases
                    WHERE purchase_token = %s
                    LIMIT 1
                    """,
                    (purchase_token,)
                )
                existing_purchase = cur.fetchone()

                if existing_purchase:
                    conn.rollback()
                    print(
                        f"SC_BILLING already processed "
                        f"purchase_id={existing_purchase['id']} "
                        f"product_id={existing_purchase['product_id']}"
                    )
                    return jsonify({
                        "success": True,
                        "message": "Purchase already processed",
                        "data": {
                            "already_processed": True,
                            "user_id": user["id"],
                            "app_user_id": user["app_user_id"],
                            "points_balance": user["points_balance"],
                            "purchase_id": existing_purchase["id"],
                            "product_id": existing_purchase["product_id"],
                            "purchase_token": existing_purchase["purchase_token"],
                            "google_acknowledgement_state": acknowledgement_state,
                        }
                    }), 200

                new_balance = int(user["points_balance"]) + int(points_to_grant)

                cur.execute(
                    """
                    INSERT INTO purchases (
                        user_id,
                        platform,
                        product_id,
                        purchase_token,
                        order_id,
                        package_name,
                        purchase_state,
                        amount_jpy,
                        points_granted,
                        raw_response_json,
                        purchased_at,
                        verified_at
                    ) VALUES (
                        %s, 'google_play', %s, %s, %s, %s,
                        'purchased', NULL, %s, %s, NOW(), NOW()
                    )
                    """,
                    (
                        user["id"],
                        product_id,
                        purchase_token,
                        order_id,
                        package_name,
                        points_to_grant,
                        json.dumps(play_response, ensure_ascii=False),
                    )
                )
                purchase_id = cur.lastrowid

                cur.execute(
                    """
                    UPDATE users
                    SET points_balance = %s
                    WHERE id = %s
                    """,
                    (new_balance, user["id"])
                )

                cur.execute(
                    """
                    INSERT INTO point_transactions (
                        user_id,
                        transaction_type,
                        points_delta,
                        balance_after,
                        related_purchase_id,
                        source_type,
                        source_id,
                        note
                    ) VALUES (
                        %s, 'purchase', %s, %s, %s, 'google_play', %s, %s
                    )
                    """,
                    (
                        user["id"],
                        points_to_grant,
                        new_balance,
                        purchase_id,
                        purchase_token,
                        f"Verified by Google Play: {product_id}"
                    )
                )

                conn.commit()
                print(
                    f"SC_BILLING points granted "
                    f"user_id={user['id']} product_id={product_id} "
                    f"grant={points_to_grant} balance={new_balance} "
                    f"purchase_id={purchase_id}"
                )

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        ack_result = "skipped_already_acknowledged"
        if acknowledgement_state == 0:
            try:
                acknowledge_google_play_product_purchase(
                    package_name=package_name,
                    product_id=product_id,
                    purchase_token=purchase_token,
                )
                ack_result = "acknowledged"
                print(f"SC_BILLING acknowledge ok product_id={product_id} order_id={order_id}")
            except HttpError as e:
                ack_result = f"ack_failed: {str(e)}"
                print(f"SC_BILLING acknowledge failed error={str(e)}")

        return jsonify({
            "success": True,
            "message": "Purchase verified and points granted",
            "data": {
                "already_processed": False,
                "user_id": user["id"],
                "app_user_id": app_user_id,
                "product_id": product_id,
                "purchase_token": purchase_token,
                "order_id": order_id,
                "granted_points": points_to_grant,
                "points_balance": new_balance,
                "purchase_id": purchase_id,
                "google_purchase_state": purchase_state,
                "google_acknowledgement_state": acknowledgement_state,
                "ack_result": ack_result,
                "google_response": play_response,
            }
        }), 200

    except Exception as e:
        print(f"SC_BILLING billing_verify exception error={str(e)}")
        return jsonify({
            "success": False,
            "message": "billing_verify failed",
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
