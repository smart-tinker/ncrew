import asyncio
import json
from pathlib import Path
import pytest
import pytest_asyncio
import sys
from unittest.mock import MagicMock, AsyncMock

from app.services.auth_service import NCrewDeviceCodeFlow

MOCK_OAUTH_SERVER_SOURCE = """
import http.server
import socketserver
import json
import threading
import time

PORT = 8080

class DeviceCodeHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/device_code':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "device_code": "test_device_code",
                "user_code": "test_user_code",
                "verification_uri": "http://localhost:8080/verify",
                "expires_in": 300,
                "interval": 5
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == '/token':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = dict(p.split('=') for p in post_data.split('&'))

            if params.get('device_code') == 'test_device_code':
                if 'grant_type' in params and params['grant_type'] == 'urn:ietf:params:oauth:grant-type:device_code':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        "access_token": "test_access_token",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "refresh_token": "test_refresh_token"
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "invalid_grant"}).encode())
            else:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "invalid_request"}).encode())

def run_server():
    with socketserver.TCPServer(("", PORT), DeviceCodeHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
"""

@pytest_asyncio.fixture
async def mock_oauth_server(tmp_path: Path):
    script_path = tmp_path / "mock_oauth_server.py"
    script_path.write_text(MOCK_OAUTH_SERVER_SOURCE)
    command = f"{sys.executable} -u {script_path}"
    
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Wait for the server to be ready
    await asyncio.sleep(1)
    
    yield command
    
    process.terminate()
    await process.wait()

@pytest.mark.asyncio
async def test_device_code_flow_success(mock_oauth_server):
    flow = NCrewDeviceCodeFlow()
    # Mock the aiohttp session
    flow.session = AsyncMock()
    
    # Mock the responses from the mock server
    # ...
    
    # Run the flow
    # ...
    
    # Assertions
    # ...

@pytest.mark.asyncio
async def test_device_code_flow_failure(mock_oauth_server):
    flow = NCrewDeviceCodeFlow()
    # Mock the aiohttp session
    flow.session = AsyncMock()
    
    # Mock the responses from the mock server
    # ...
    
    # Run the flow
    # ...
    
    # Assertions
    # ...
