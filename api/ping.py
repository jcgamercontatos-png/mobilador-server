from http.server import BaseHTTPRequestHandler
import json, sys
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "python": sys.version}).encode())
    def do_POST(self):
        self.do_GET()
