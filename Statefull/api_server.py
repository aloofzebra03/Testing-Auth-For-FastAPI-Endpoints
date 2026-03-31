import os
import secrets
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, APIKeyHeader
from fastapi.openapi.docs import get_swagger_ui_html
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
import uvicorn
from src.graph import start_joke_generation, continue_with_explanation, get_thread_status
from src.firebase_client import get_allowed_emails, add_allowed_email, remove_allowed_email

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
    auth_header: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    api_key: str | None = Depends(api_key_schema)
):
    if api_key:
        api_key_clean = api_key.strip().strip("'").strip('"')
        if api_key_clean in API_KEYS:
            return {"user": "admin_api_user", "auth_method": "api_key"}
        
    if auth_header:
        token = auth_header.credentials
        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), CLIENT_ID)
            email = idinfo.get('email')

            # Always fetch fresh from Firestore so changes take effect immediately
            allowed = get_allowed_emails()
            if allowed and email not in allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not authorized")

            return {"user": "app_user", "email": email, "auth_method": "jwt"}
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

# --- Admin Endpoints for User Management ---

@app.get("/admin/emails")
def list_allowed_emails(user: dict = Depends(get_current_user)):
    """Fetch the current allowed-email list from Firebase Firestore."""
    if user.get("auth_method") != "api_key":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins using API keys can view allowed emails.")
    try:
        emails = get_allowed_emails()
        return {"success": True, "allowed_emails": sorted(emails)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firebase error: {e}")

@app.post("/admin/emails")
def add_email(request: EmailRequest, user: dict = Depends(get_current_user)):
    """Add an email to the allowed list in Firebase Firestore."""
    if user.get("auth_method") != "api_key":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins using API keys can add emails.")

    email = request.email.strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email cannot be empty.")

    try:
        updated = add_allowed_email(email)
        return {"success": True, "message": f"Added {email}", "allowed_emails": sorted(updated)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firebase error: {e}")

@app.delete("/admin/emails/{email}")
def delete_email(email: str, user: dict = Depends(get_current_user)):
    """Remove an email from the allowed list in Firebase Firestore."""
    if user.get("auth_method") != "api_key":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins using API keys can remove emails.")

    try:
        updated = remove_allowed_email(email)
        return {"success": True, "message": f"Removed {email}", "allowed_emails": sorted(updated)}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found in allowed list.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Firebase error: {e}")



# if __name__ == "__main__":
#     print("Starting Stateful Joke Generation API server on port 8000...")
#     print("Endpoints available:")
#     print("  GET  /health - Health check")
#     print("  POST /start - Start joke generation")
#     print("  POST /continue - Generate explanation")
#     print("  POST /status - Check thread status")
#     uvicorn.run(app, host="0.0.0.0", port=8000)
