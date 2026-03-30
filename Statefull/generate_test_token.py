import http.server
import socketserver
import os
import webbrowser
from dotenv import load_dotenv

# Load env file to get CLIENT_ID
load_dotenv()
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

PORT = 8080

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Google JWT Test Generator</title>
    <script src="https://accounts.google.com/gsi/client" async defer></script>
</head>
<body style="font-family: Arial, sans-serif; margin: 40px; background-color: #f0f4f8;">
    <h2>Generate a Real Test Google JWT</h2>
    <p><i>Note: You must ensure <b>http://localhost:{PORT}</b> is listed under "Authorized JavaScript origins" in your Google Cloud Console for the Client ID: {CLIENT_ID}</i></p>
    
    <div id="g_id_onload"
         data-client_id="{CLIENT_ID}"
         data-callback="handleCredentialResponse">
    </div>
    <div class="g_id_signin" data-type="standard"></div>

    <h3 style="margin-top:30px;">Your Fresh Token (Copy & Paste to Swagger):</h3>
    <textarea id="tokenBox" rows="10" cols="100" style="padding:10px; font-family: monospace;" placeholder="Sign in above and your fresh JWT token will appear here..."></textarea>

    <script>
      function handleCredentialResponse(response) {{
         document.getElementById("tokenBox").value = response.credential;
      }}
    </script>
</body>
</html>
"""

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html_content.encode())

if __name__ == "__main__":
    if not CLIENT_ID or "your-google-client-id" in CLIENT_ID:
        print("ERROR: Please set a valid GOOGLE_CLIENT_ID in your .env file first!")
        exit(1)
        
    print(f"Starting standalone token generator on port {PORT}...")
    with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
        print(f"Opening your browser to: http://localhost:{PORT}")
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\\nShutting down...")
