# FastAPI Backend Authentication Guide

This document details exactly how authentication is implemented and enforced on the FastAPI backend, and how client application explicitly (e.g., Android app developers) should interact with it securely.

## Overview

The API (`/start`, `/continue`, `/status`) requires authentication on every request. It supports two primary methods of authentication:

1. **Google ID Tokens (JWT)**: Meant for end-users interacting via the mobile application.
2. **API Keys**: Meant for backend services, automation scripts, and administrative access.

Additionally, the generated documentation (`/docs`) is guarded by HTTP Basic Authentication.

---

## 1. End-User Authentication (Mobile App Integration)

When a regular user interacts with the app, we utilize **Google Sign-In / Firebase Authentication** accompanied by a strict Firestore validation check.

### How It Works (Backend Logic)

1. **Token Verification**: The server extracts the Bearer token from the `Authorization` header and strictly verifies its cryptographical signature using the `google.oauth2.id_token` class against our `GOOGLE_CLIENT_ID`.
2. **Account Validation**: Once the token is verified, the server extracts the user's `email`. It then queries our Firebase Firestore database using a rapid O(1) point-read.
3. **Database Check**: The server checks if a document with that exact `email` address exists as the **Document ID** inside the `users` collection.
4. **Access Granted/Denied**: If the document exists, the user is authorized. If the document does not exist, a `403 Forbidden` is returned indicating they must be a registered user.

### Developer Integration Instructions

If you are developing the mobile frontend/app, follow these exact steps to hit the API:

1. **Sign the User In**: Authenticate the user on the device using Google Sign-In or Firebase Auth.
2. **Register the User**: Ensure your app creates a document inside the `users` Firestore collection.
   - **CRITICAL:** The Document ID for this entry **must** be the user's email address (e.g., `user@gmail.com`). This is how the server checks if they are authorized.
3. **Obtain an ID Token**: Ask the Google/Firebase SDK for the user's current JWT ID Token.
4. **Attach to Headers**: Send HTTP requests to the FastAPI endpoints providing the token in the headers as follows:
   ```http
   Authorization: Bearer <YOUR_GOOGLE_ID_TOKEN>
   ```

**Expected Error Codes:**

- `401 Unauthorized`: You forgot the `Authorization` header, the token expired, or the token is invalid/tampered with.
- `403 Forbidden`: The token is valid, but the user's email was not found in the Firestore `users` collection. (The mobile app might have failed to register them correctly in Firestore).

---

## 2. Administrator / Service Authentication

If you need to hit the API programmatically (for example, from a script, cron job, or admin dashboard) without simulating a real mobile App User, you can bypass the JWT check using an API Key.

### Developer Integration Instructions

Send your HTTP request with the `X-API-Key` header populated:

```http
X-API-Key: super-secret-key-1
```

*Note: The valid API keys are configured strictly in the backend `.env` file under the `API_KEYS` comma-separated array.*

---

## 3. Accessing API Documentation

The OpenAPI Specification (`/openapi.json`) and Swagger UI testing portal (`/docs`) are not open to the public internet to prevent reverse engineering.

To view the `/docs`, simply navigate to the URL in your browser. A standard browser modal will prompt you for a username and password.

By default, these are controlled in your `.env` file:

- **Username**: defined by `DOCS_USERNAME`
- **Password**: defined by `DOCS_PASSWORD`

---

## 4. Backend Configuration & Setup (.env)

For the authentication layer to govern traffic correctly, the backend server must be initialized with the following keys in its `.env` file:

```env
# The Google Client ID of the Android App (used to verify the audience of the JWTs)
GOOGLE_CLIENT_ID="***.apps.googleusercontent.com"

# The Secret keys allowed to bypass user authentication completely
API_KEYS="key-1,key-2"

# Backend Firebase Service Account (Allows the server to securely read the 'users' collection)
FIREBASE_SERVICE_ACCOUNT_JSON='{"type": "service_account", "project_id": "eduai-e090e", ...}'

# Optional: Alternatively, you can provide an absolute path to the downloaded JSON key file
# FIREBASE_SERVICE_ACCOUNT_PATH="/path/to/serviceAccountKey.json"

# Basic Auth credentials for /docs access
DOCS_USERNAME="admin"
DOCS_PASSWORD="password"
```

### Note on Firebase Backend Initialization

The server establishes its own administrative connection to Firebase natively on startup. It uses the `src/firebase_client.py` module to securely wrap Google's Python SDK, favoring the injection of a stringified minified JSON object (`FIREBASE_SERVICE_ACCOUNT_JSON`) for optimal compatibility perfectly suited for AWS deployments.
