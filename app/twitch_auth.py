import logging
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from PySide6.QtCore import QObject, Signal, Slot, QThread

from app.twitch_credentials import TwitchCredentialStore

logger = logging.getLogger(__name__)

OAUTH_PORT = 17846
REDIRECT_URI = f"http://localhost:{OAUTH_PORT}/auth/twitch/callback"

HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head><title>Twitch Auth</title></head>
<body>
    <h2>Authorizing...</h2>
    <script>
        const hash = window.location.hash;
        if (hash) {
            const params = new URLSearchParams(hash.substring(1));
            const token = params.get('access_token');
            const state = params.get('state');
            if (token && state) {
                fetch('/auth/twitch/callback', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({access_token: token, state: state})
                }).then(() => {
                    document.body.innerHTML = "<h2>Authorization Successful! You can close this window.</h2>";
                }).catch(() => {
                    document.body.innerHTML = "<h2>Failed to send token to application.</h2>";
                });
            } else {
                document.body.innerHTML = "<h2>Authorization Failed: Missing token or state.</h2>";
            }
        } else {
            document.body.innerHTML = "<h2>Authorization Failed: No fragment found.</h2>";
        }
    </script>
</body>
</html>
"""

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Disable default logging to keep token out of console
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode('utf-8'))

    def do_POST(self):
        if self.path == '/auth/twitch/callback':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                import json
                body = self.rfile.read(content_length).decode('utf-8')
                try:
                    data = json.loads(body)
                    self.server.token_received = data.get('access_token')
                    self.server.state_received = data.get('state')
                except json.JSONDecodeError:
                    pass
            
            self.send_response(200)
            self.end_headers()
            
            # Flag to stop the loop
            self.server._is_shutting_down = True

class TwitchAuthWorker(QObject):
    auth_success = Signal(str, str) # login, user_id
    auth_failed = Signal(str)

    def __init__(self, client_id: str):
        super().__init__()
        self.client_id = client_id.strip()

    @Slot()
    def start_oauth(self):
        # Если client_id не задан в конфиге, используем жестко заданный (работает из коробки)
        effective_client_id = self.client_id if self.client_id else "4tvblbz0dp1v9pgufiz3oaqg8vxphl"
        
        state = secrets.token_urlsafe(16)
        
        # Start local server
        server = HTTPServer(('127.0.0.1', OAUTH_PORT), OAuthCallbackHandler)
        server.token_received = None
        server.state_received = None
        
        # Open browser
        params = {
            "response_type": "token",
            "client_id": effective_client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": "chat:read chat:edit",
            "state": state
        }
        auth_url = f"https://id.twitch.tv/oauth2/authorize?{urllib.parse.urlencode(params)}"
        webbrowser.open(auth_url)
        
        logger.info("Waiting for OAuth callback...")
        # Serve with timeout
        server.timeout = 1.0
        timeout_at = time.time() + 120.0
        
        while time.time() < timeout_at and server.token_received is None and not getattr(server, '_is_shutting_down', False):
            server.handle_request()
            
        token = server.token_received
        received_state = server.state_received
        server.server_close()
        
        if not token or not received_state:
            self.auth_failed.emit("Auth timed out or was aborted.")
            return
            
        if not secrets.compare_digest(state, received_state):
            self.auth_failed.emit("State mismatch. Potential CSRF attack.")
            return
            
        # Verify token and get user profile
        try:
            with httpx.Client(timeout=10) as client:
                res = client.get("https://api.twitch.tv/helix/users", headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": effective_client_id
                })
                res.raise_for_status()
                data = res.json()
                if not data.get("data"):
                    self.auth_failed.emit("No user profile found for token.")
                    return
                    
                user_info = data["data"][0]
                login = user_info["login"]
                user_id = user_info["id"]
                
                TwitchCredentialStore.set_token(token)
                self.auth_success.emit(login, user_id)
        except Exception as e:
            logger.error(f"Failed to verify Twitch token: {e}")
            self.auth_failed.emit(f"Token verification failed: {e}")
