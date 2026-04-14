import os
import secrets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, APIKeyHeader
from fastapi.openapi.docs import get_swagger_ui_html
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
import uvicorn
from src.graph import start_joke_generation, continue_with_explanation, get_thread_status
from src.firebase_client import is_email_allowed, check_and_increment_rate_limit, DAILY_REQUEST_LIMIT

load_dotenv()

# Auth Configuration
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
API_KEYS = set(k.strip().strip("'").strip('"') for k in filter(None, os.getenv("API_KEYS", "").split(",")))
DOCS_USERNAME = os.getenv("DOCS_USERNAME", "admin")
DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "password")

security_bearer = HTTPBearer(auto_error=False)
security_basic = HTTPBasic()
api_key_schema = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_current_user(
    response: Response,
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    api_key: str | None = Depends(api_key_schema)
):
    if api_key:
        api_key_clean = api_key.strip().strip("'").strip('"')
        if api_key_clean in API_KEYS:
            # API key users are internal/admin — not subject to rate limiting
            return {"user": "admin_api_user", "auth_method": "api_key"}
        
    if auth_header:
        token = auth_header.credentials
        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), CLIENT_ID)
            email = idinfo.get('email')

            # 1. Verify the email is a registered user in Firestore 'users' collection
            if not is_email_allowed(email):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not authorized: Must be a registered user.")

            # 2. Enforce per-email daily rate limit
            new_count, remaining, limit_exceeded = check_and_increment_rate_limit(email)

            # Always add rate-limit headers so the client can display usage
            response.headers["X-RateLimit-Limit"]     = str(DAILY_REQUEST_LIMIT)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Policy"]    = f"{DAILY_REQUEST_LIMIT};w=86400"  # 86400s = 1 day

            if limit_exceeded:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Daily limit of {DAILY_REQUEST_LIMIT} requests exceeded. "
                        "Counter resets at midnight IST (Indian Standard Time)."
                    ),
                    headers={
                        "X-RateLimit-Limit":     str(DAILY_REQUEST_LIMIT),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Policy":    f"{DAILY_REQUEST_LIMIT};w=86400",
                        "Retry-After":           "86400",
                    }
                )

            return {"user": "app_user", "email": email, "auth_method": "jwt",
                    "requests_today": new_count, "requests_remaining": remaining}
        except HTTPException:
            raise  # re-raise 403 / 429 as-is
        except ValueError as e:
            print(f"JWT Verification Error: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google JWT token")
            
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, 
        detail="Missing or invalid authentication credentials"
    )

def get_docs_username(credentials: HTTPBasicCredentials = Depends(security_basic)):
    correct_username = secrets.compare_digest(credentials.username, DOCS_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, DOCS_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Create stateful FastAPI app
app = FastAPI(
    title="Stateful Joke Generation API", 
    version="2.0.0",
    description="API with persistent state management for joke generation",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_docs_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

@app.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_docs_username)):
    return app.openapi()

# Request models
class StartRequest(BaseModel):
    topic: str
    thread_id: str

class ContinueRequest(BaseModel):
    thread_id: str

class StatusRequest(BaseModel):
    thread_id: str

class EmailRequest(BaseModel):
    email: str

@app.get("/")
def read_root():
    return {
        "message": "Stateful Joke Generation API is running!",
        "version": "2.0.0(Statefull)",
        "endpoints": [
            "/health",
            "/start - Start joke generation",
            "/continue - Generate explanation",
            "/status - Check thread status"
        ]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "persistence": "SQLite"}

@app.post("/start")
def start_endpoint(request: StartRequest, user: dict = Depends(get_current_user)):
    try:
        print(f"API /start - topic: {request.topic}, thread: {request.thread_id}")
        result = start_joke_generation(request.topic, request.thread_id)
        
        return {
            "success": True,
            "thread_id": result['thread_id'],
            "topic": result['topic'],
            "joke": result['joke'],
            "status": result['status'],
            "message": "Joke generated. Call /continue to get explanation."
        }
    except Exception as e:
        print(f"API error in /start: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/continue")
def continue_endpoint(request: ContinueRequest, user: dict = Depends(get_current_user)):
    try:
        print(f"API /continue - thread: {request.thread_id}")
        result = continue_with_explanation(request.thread_id)
        
        return {
            "success": True,
            "thread_id": result['thread_id'],
            "topic": result['topic'],
            "joke": result['joke'],
            "explanation": result['explanation'],
            "status": result['status'],
            "message": "Workflow completed."
        }
    except ValueError as e:
        print(f"API validation error in /continue (Invalid thread id): {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"API error in /continue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/status")
def status_endpoint(request: StatusRequest, user: dict = Depends(get_current_user)):
    try:
        print(f"API /status - thread: {request.thread_id}")
        result = get_thread_status(request.thread_id)
        
        if not result.get('exists'):
            raise HTTPException(status_code=404, detail=result.get('message'))
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"API error in /status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# The mobile app natively handles creating user documents in the 'users' collection.



# if __name__ == "__main__":
#     print("Starting Stateful Joke Generation API server on port 8000...")
#     print("Endpoints available:")
#     print("  GET  /health - Health check")
#     print("  POST /start - Start joke generation")
#     print("  POST /continue - Generate explanation")
#     print("  POST /status - Check thread status")
#     uvicorn.run(app, host="0.0.0.0", port=8000)
