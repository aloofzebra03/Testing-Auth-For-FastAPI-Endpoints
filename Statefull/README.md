# FastAPI — JWT Auth + Per-Email Rate Limiting via Firebase

## Purpose

This repository is a working proof-of-concept for:

1. **Google JWT authentication** on a FastAPI server — verifying ID tokens issued by Google's OAuth 2.0 infrastructure (e.g. from an Android app using Credential Manager)
2. **Email-based authorization** — checking that the authenticated email belongs to a registered user stored in Firestore
3. **Per-email rate limiting** — enforcing a daily request cap (currently `DAILY_REQUEST_LIMIT = 3` for testing, production value is 100) using atomic Firestore transactions, shared correctly across Docker container restarts and multiple replicas

The joke-generation workflow (LangGraph + Gemini) is the **test payload** — something that requires auth to call. The auth and rate-limiting layers are the focus.

---

## How the Auth Pipeline Works

Every protected endpoint runs `get_current_user()` as a FastAPI dependency. The flow is:

```
Incoming request
       │
       ├─ X-API-Key header present?
       │     └─ Yes → validate against API_KEYS env var → allow (no rate limit)
       │
       └─ Authorization: Bearer <token> header present?
             └─ Yes → verify Google ID token (JWT)
                   │
                   ├─ Signature invalid / expired → HTTP 401
                   │
                   ├─ Email not in Firestore users/{email} → HTTP 403
                   │
                   ├─ Daily counter > DAILY_REQUEST_LIMIT → HTTP 429
                   │
                   └─ All checks pass → allow request, attach X-RateLimit-* headers
```

---

## ⚠️ Critical: Google Client ID Must Match

The `GOOGLE_CLIENT_ID` in your `.env` **must be the exact same OAuth 2.0 client ID** that was used to generate the JWT token on the client side.

- On Android: the client ID configured in `GoogleIdTokenRequestOptions` (passed to `GetGoogleIdOption`)
- On the web (`generate_test_token.py`): the `data-client_id` attribute on the Google Sign-In button

**If they don't match, `id_token.verify_oauth2_token()` will throw a `ValueError` and you'll get HTTP 401.**

The server verifies:
1. The token signature is valid (signed by Google's private keys — fetched from `https://www.googleapis.com/oauth2/v3/certs`)
2. The `aud` (audience) claim in the token equals your `GOOGLE_CLIENT_ID`
3. The token is not expired (`exp` claim)

All of this is handled by `google-auth`'s `id_token.verify_oauth2_token()`. The `email` is then read directly from the decoded payload — no separate decoding step is needed.

---

## Firestore Structure

Two collections are used:

### `users/` — Registration / Authorization

```
Collection: users
  Document ID: <email address>   e.g. "aryan@gmail.com"
    (any fields — the server only checks doc.exists)
```

The mobile app creates user documents. The server does an O(1) point-read — if the document exists, the email is authorized.

### `rate_limits/` — Daily Request Counters

```
Collection: rate_limits
  Document ID: "<email>:<YYYY-MM-DD>"   e.g. "aryan@gmail.com:2026-04-14"
    email : "aryan@gmail.com"
    date  : "2026-04-14"          ← IST calendar date (UTC+5:30)
    count : 47                    ← atomically incremented per request
```

- The date is always the **IST calendar date**, so the counter resets at **midnight IST**
- Each new calendar day produces a new document — no cleanup needed day-to-day
- The counter is incremented inside a **Firestore transaction**, so concurrent requests cannot race past the limit

---

## 📁 File Structure

```
Statefull/
├── api_server.py              # FastAPI app: auth dependency, rate limiting, endpoints
├── Dockerfile                 # Production Docker image (AWS EC2 / ECS ready)
├── requirements-simple.txt    # Pinned runtime deps used by the Dockerfile
│
├── src/
│   ├── firebase_client.py    # Firebase init, is_email_allowed(), check_and_increment_rate_limit()
│   ├── graph.py              # LangGraph workflow (test payload)
│   ├── core.py               # Joke / explanation generators
│   ├── models.py             # LangGraph state type
│   └── config.py             # LLM (Gemini) configuration
│
├── generate_test_token.py     # Local web page that signs in with Google and prints the JWT
├── test_api.py                # Manual/automated HTTP test calls
└── .env                       # Runtime secrets — never committed
```

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` | ✅ | OAuth 2.0 Web Client ID — **must match the client ID used to issue the JWT** |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | ✅ (Docker/AWS) | Entire Firebase service account JSON as a minified single-line string |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | ✅ (local alt.) | Path to the Firebase service account `.json` file |
| `API_KEYS` | ✅ | Comma-separated static API keys for admin/internal callers (bypass rate limit) |
| `GOOGLE_API_KEY` | ✅ | Gemini API key (only needed for the joke-generation test payload) |
| `DOCS_USERNAME` | optional | HTTP Basic Auth username for `/docs` (default: `admin`) |
| `DOCS_PASSWORD` | optional | HTTP Basic Auth password for `/docs` (default: `password`) |

> **Docker/AWS**: Pass `FIREBASE_SERVICE_ACCOUNT_JSON` as a single-line JSON string via `--env-file .env` or AWS Secrets Manager. The `firebase_client.py` handles the `\n` → newline fix for the private key automatically.

---

## 🚀 Running the Server

### Local

```bash
cd Statefull
pip install -r requirements-simple.txt
# fill in .env
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker build -t jwt-rate-limit-api .
docker run -p 8000:8000 --env-file .env jwt-rate-limit-api
```

---

## 🧪 Generating a Test JWT

The `generate_test_token.py` script spins up a local HTTP server on port 8080 and opens a Google Sign-In page in your browser.

```bash
python generate_test_token.py
```

**Before running:**
1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Open your OAuth 2.0 Web Client
3. Add `http://localhost:8080` to **Authorized JavaScript origins**
4. Make sure `GOOGLE_CLIENT_ID` in `.env` is this same client ID

After signing in, the page displays the raw JWT string. Copy it and use it as:
```
Authorization: Bearer <token>
```

The token expires in ~1 hour. Re-run the script to get a fresh one.

---

## 🔌 API Endpoints

### Public (no auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Discovery / sanity check |
| `GET` | `/health` | Liveness probe — returns `{"status": "healthy"}` |

### Protected (JWT or API key required)

| Method | Path | Description |
|---|---|---|
| `POST` | `/start` | Start joke generation for a `thread_id` |
| `POST` | `/continue` | Resume workflow from saved checkpoint |
| `POST` | `/status` | Check thread state |

### Protected (HTTP Basic Auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/docs` | Swagger UI |
| `GET` | `/openapi.json` | Raw OpenAPI schema |

---

### POST /start

```json
// Request
{ "topic": "artificial intelligence", "thread_id": "user123_session1" }

// Response (200)
{
  "success": true,
  "thread_id": "user123_session1",
  "topic": "artificial intelligence",
  "joke": "Why did the neural network go to therapy? ...",
  "status": "joke_generated",
  "message": "Joke generated. Call /continue to get explanation."
}
```

**Response headers (JWT auth only):**
```
X-RateLimit-Limit: 3
X-RateLimit-Remaining: 2
X-RateLimit-Policy: 3;w=86400
```

**When limit is exceeded (HTTP 429):**
```json
{
  "detail": "Daily limit of 3 requests exceeded. Counter resets at midnight IST (Indian Standard Time)."
}
```
```
Retry-After: 86400
X-RateLimit-Limit: 3
X-RateLimit-Remaining: 0
```

---

### POST /continue

```json
// Request
{ "thread_id": "user123_session1" }

// Response (200)
{
  "success": true,
  "thread_id": "user123_session1",
  "joke": "Why did the neural network go to therapy? ...",
  "explanation": "This joke works because ...",
  "status": "completed",
  "message": "Workflow completed."
}
```

---

### POST /status

```json
// Request
{ "thread_id": "user123_session1" }

// Response (200)
{
  "success": true,
  "exists": true,
  "status": "joke_generated",
  "has_joke": true,
  "has_explanation": false,
  "next_node": "generate_explanation"
}
```

---

## ✅ What's Implemented & Verified

| Feature | Detail |
|---|---|
| Google JWT verification | `id_token.verify_oauth2_token()` — validates signature, audience, expiry |
| Email extraction from JWT | `idinfo['email']` from the decoded token payload |
| Firestore email allowlist | O(1) point-read on `users/{email}` — HTTP 403 if doc doesn't exist |
| API key auth | `X-API-Key` header, validated against `API_KEYS` env var |
| Per-email daily rate limit | Atomic Firestore transaction on `rate_limits/{email}:{IST-date}` |
| IST-based daily reset | Counter tied to IST calendar date — resets at midnight IST |
| `X-RateLimit-*` headers | Attached to every JWT-auth response so clients can display usage |
| HTTP 429 with `Retry-After` | Returned when `count > DAILY_REQUEST_LIMIT` |
| Docs Basic Auth | `/docs` and `/openapi.json` require HTTP Basic credentials |
| Docker support | Dockerfile tested; secrets passed via `--env-file` at runtime |
| Firebase credentials (Docker) | `FIREBASE_SERVICE_ACCOUNT_JSON` env var with `\n` fix for private key |

---

## ❌ Why Not a Local File for Rate Limiting?

| | Local file | Firestore |
|---|---|---|
| Container restart | File wiped → counters reset | Persists forever |
| 2+ container replicas | Each has its own file → limit never enforced | Single shared truth |
| Setup overhead | None | Already needed for auth |

Since Firestore is already used for email allowlisting, the rate limit counter adds zero new infrastructure.

---

## 🐛 Troubleshooting

### HTTP 401 — Invalid Google JWT
- `GOOGLE_CLIENT_ID` in `.env` doesn't match the client ID used to generate the token
- Token has expired (they last ~1 hour) — re-run `generate_test_token.py`
- `http://localhost:8080` is not listed in Authorized JavaScript origins in Google Cloud Console

### HTTP 403 — Email not authorized
- The authenticated email doesn't have a document in the Firestore `users` collection
- Add a document with the email as the document ID to the `users` collection in Firebase Console

### HTTP 429 — Rate limit exceeded
- The email has hit `DAILY_REQUEST_LIMIT` requests today (IST)
- To reset during testing: delete the document `rate_limits/{email}:{today-IST}` in Firebase Console
- To change the limit: edit `DAILY_REQUEST_LIMIT` in `src/firebase_client.py`

### Firebase EnvironmentError on startup
- Neither `FIREBASE_SERVICE_ACCOUNT_JSON` nor `FIREBASE_SERVICE_ACCOUNT_PATH` is set
- If using JSON string in `.env`, make sure it's all on one line (no literal newlines)

### Port 8000 already in use
```bash
netstat -ano | findstr :8000   # Windows
lsof -i :8000                  # Linux/Mac
```
