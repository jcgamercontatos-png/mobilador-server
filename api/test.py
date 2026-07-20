import sys, json
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            import bcrypt
            bcrypt_ok = 'ok'
            bcrypt_hash = bcrypt.hashpw(b'test', bcrypt.gensalt()).decode()
        except Exception as e:
            bcrypt_ok = f'fail: {e}'
            bcrypt_hash = ''
        try:
            from fastapi import FastAPI
            fastapi_ok = 'ok'
        except Exception as e:
            fastapi_ok = f'fail: {e}'
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import declarative_base
            engine = create_engine('sqlite:////tmp/test.db', connect_args={'check_same_thread': False})
            engine.connect()
            engine.dispose()
            sqlite_ok = 'ok'
        except Exception as e:
            sqlite_ok = f'fail: {e}'
        data = {
            'python': sys.version,
            'bcrypt': bcrypt_ok,
            'fastapi': fastapi_ok,
            'sqlite': sqlite_ok
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
