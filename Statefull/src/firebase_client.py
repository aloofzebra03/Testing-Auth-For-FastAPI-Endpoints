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

def get_allowed_emails() -> Set[str]:
    """
    Fetch the current set of allowed emails from Firestore.
    Returns an empty set if the document does not exist.
    """
    try:
        db = _get_db()
        doc = db.collection(_COLLECTION).document(_DOCUMENT).get()
        if doc.exists:
            emails = doc.to_dict().get(_FIELD, [])
            return set(e.strip().lower() for e in emails if e.strip())
        else:
            logger.warning(
                f"Firestore document '{_COLLECTION}/{_DOCUMENT}' not found. "
                "Returning empty email set. Create it in the Firebase Console."
            )
            return set()
    except Exception as e:
        logger.error(f"Failed to fetch allowed emails from Firestore: {e}")
        raise


def add_allowed_email(email: str) -> Set[str]:
    """
    Add an email to the Firestore allowed list.
    Creates the document if it does not exist.
    Returns the updated set of emails.
    """
    email = email.strip().lower()
    try:
        db = _get_db()
        ref = db.collection(_COLLECTION).document(_DOCUMENT)
        # Use set with merge=True so we don't overwrite unrelated fields
        ref.set(
            {_FIELD: firestore.ArrayUnion([email])},
            merge=True
        )
        logger.info(f"Added email to Firestore: {email}")
        return get_allowed_emails()
    except Exception as e:
        logger.error(f"Failed to add email to Firestore: {e}")
        raise


def remove_allowed_email(email: str) -> Set[str]:
    """
    Remove an email from the Firestore allowed list.
    Returns the updated set of emails.
    Raises KeyError if the email is not present.
    """
    email = email.strip().lower()
    try:
        db = _get_db()
        current = get_allowed_emails()
        if email not in current:
            raise KeyError(f"Email '{email}' not found in allowed list.")

        ref = db.collection(_COLLECTION).document(_DOCUMENT)
        ref.update({_FIELD: firestore.ArrayRemove([email])})
        logger.info(f"Removed email from Firestore: {email}")
        return get_allowed_emails()
    except KeyError:
        raise
    except Exception as e:
        logger.error(f"Failed to remove email from Firestore: {e}")
        raise
