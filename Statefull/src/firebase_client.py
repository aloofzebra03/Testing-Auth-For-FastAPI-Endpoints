"""
Firebase Firestore client for managing allowed emails.

Firestore structure:
  Collection: "auth"
    Document: "allowed_emails"
      Field: "emails" -> list of lowercase email strings

Setup:
  1. Go to Firebase Console -> Project Settings -> Service Accounts
  2. Click "Generate new private key" -> download the JSON file
  3. Set FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/serviceAccountKey.json in .env
     OR set FIREBASE_SERVICE_ACCOUNT_JSON with the JSON content directly (good for Docker/cloud)
"""

import os
import json
import logging
from typing import Set

import firebase_admin
from firebase_admin import credentials, firestore

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
