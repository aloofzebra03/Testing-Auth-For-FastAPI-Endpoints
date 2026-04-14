"""
Firebase Firestore client for:
  - Managing allowed emails (user authorization)
  - Per-email daily rate limiting (100 requests/day)

Firestore structure:
  Collection: "users"
    Document: <email>   ← authorization check (O(1) point read)

  Collection: "rate_limits"
    Document: "{email}:{YYYY-MM-DD}"  ← one doc per user per UTC day
      Fields:
        email      : str
        date       : str  (YYYY-MM-DD UTC)
        count      : int  (atomic counter, incremented per request)

Setup:
  1. Go to Firebase Console -> Project Settings -> Service Accounts
  2. Click "Generate new private key" -> download the JSON file
  3. Set FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/serviceAccountKey.json in .env
     OR set FIREBASE_SERVICE_ACCOUNT_JSON with the JSON content directly (good for Docker/cloud)
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Set, Tuple

# Indian Standard Time — UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import firestore as google_firestore

logger = logging.getLogger(__name__)

# Firestore path constants
_COLLECTION = "auth"
_DOCUMENT   = "allowed_emails"
_FIELD      = "emails"

_db = None  # Firestore client (lazy-initialized)


def _get_db():
    """Initialize Firebase app and return a Firestore client (singleton)."""
    global _db
    if _db is not None:
        return _db

    if firebase_admin._apps:
        # Already initialized (e.g., in tests)
        _db = firestore.client()
        return _db

    # --- Credentials: prefer inline JSON, fall back to file path ---
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if service_account_json:
        info = json.loads(service_account_json)
        # python-dotenv can mangle \n into literal \\n inside the private key.
        # Fix it so OpenSSL can parse the PEM certificate correctly.
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        cred = credentials.Certificate(info)
        logger.info("Firebase: using inline service-account JSON from env var.")
    elif service_account_path:
        cred = credentials.Certificate(service_account_path)
        logger.info(f"Firebase: using service-account file at {service_account_path}")
    else:
        raise EnvironmentError(
            "Firebase credentials not found. Set either "
            "FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON "
            "in your .env file."
        )

    firebase_admin.initialize_app(cred)
    _db = firestore.client()
    logger.info("Firebase initialized successfully.")
    return _db


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Daily request limit applied to JWT (email) users
DAILY_REQUEST_LIMIT = 3


def is_email_allowed(email: str) -> bool:
    """
    Check if the given email corresponds to a registered user in the 'users' collection.
    This is an O(1) point read, which scales perfectly.
    """
    email = email.strip().lower()
    try:
        db = _get_db()
        # The document ID in the 'users' collection is the email address itself
        doc = db.collection("users").document(email).get()
        return doc.exists
    except Exception as e:
        logger.error(f"Failed to check if email '{email}' exists in Firestore: {e}")
        raise


def check_and_increment_rate_limit(
    email: str,
    daily_limit: int = DAILY_REQUEST_LIMIT,
) -> Tuple[int, int, bool]:
    """
    Atomically increment the per-email daily request counter in Firestore.

    Uses a Firestore transaction so that concurrent requests cannot race and
    send the counter past the limit without detection.

    Document key: "rate_limits/{email}:{YYYY-MM-DD}"
    The date is always UTC so the window resets at midnight UTC everywhere.

    Returns:
        (new_count, remaining, limit_exceeded)
        - new_count      : int  — value of the counter after this increment
        - remaining      : int  — requests still allowed today (0 if exceeded)
        - limit_exceeded : bool — True when new_count > daily_limit
    """
    email = email.strip().lower()
    today_ist = datetime.now(_IST).strftime("%Y-%m-%d")  # IST calendar date
    doc_id = f"{email}:{today_ist}"

    db = _get_db()
    doc_ref = db.collection("rate_limits").document(doc_id)
    transaction = db.transaction()

    @google_firestore.transactional
    def _increment(transaction: google_firestore.Transaction, ref) -> int:
        """Read-increment-write inside a single Firestore transaction."""
        snapshot = ref.get(transaction=transaction)
        current_count: int = snapshot.get("count") if snapshot.exists else 0
        new_count = current_count + 1
        transaction.set(
            ref,
            {"email": email, "date": today_ist, "count": new_count},  # IST date stored
            merge=True,
        )
        return new_count

    try:
        new_count = _increment(transaction, doc_ref)
    except Exception as e:
        logger.error(f"Rate-limit Firestore transaction failed for '{email}': {e}")
        raise

    remaining = max(0, daily_limit - new_count)
    limit_exceeded = new_count > daily_limit
    logger.info(
        f"Rate-limit | email={email} | date={today_ist} (IST) | "
        f"count={new_count}/{daily_limit} | exceeded={limit_exceeded}"
    )
    return new_count, remaining, limit_exceeded
