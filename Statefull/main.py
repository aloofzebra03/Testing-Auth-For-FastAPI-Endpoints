"""
Main application entry point for the stateful joke generation agent.
Runs the FastAPI server.
"""

import uvicorn
from api_server import app


def main():
    """Start the FastAPI server."""
    print("🎭 Starting Stateful Joke Generation API Server...")
    print("=" * 60)
    print("Endpoints:")
    print("  - GET  / - API info")
    print("  - GET  /health - Health check")
    print("  - POST /start - Start joke generation")
    print("  - POST /continue - Generate explanation")
    print("  - POST /status - Check thread status")
    print("=" * 60)
    print("Server running on http://0.0.0.0:8000")
    print("Press CTRL+C to stop")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
