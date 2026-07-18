@echo off
cd /d "%~dp0"
echo ================================
echo   MOBILADOR - ngrok Tunnel
echo ================================
echo.
echo Iniciando servidor...
start "" /B python main.py
timeout /t 3 /nobreak >nul
echo.
echo Iniciando ngrok tunnel...
python -c "
import sys, os, time, threading, webbrowser
from pyngrok import ngrok

token = os.environ.get('NGROK_AUTH_TOKEN', '')
if token:
    ngrok.set_auth_token(token)

tunnel = ngrok.connect(8000, 'http')
url = tunnel.public_url
print()
print('=' * 50)
print(f'  SERVIDOR ONLINE!')
print(f'')
print(f'  URL DO ADMIN:  {url}/admin')
print(f'')
print(f'  URL BASE APP:  {url}/')
print(f'')
print(f'  Cole a URL BASE no app Android')
print(f'')
print('=' * 50)
print()
print('Pressione CTRL+C para parar')
print()

# Salvar URL num arquivo
with open('url_publica.txt', 'w') as f:
    f.write(url)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('\nParando...')
    ngrok.kill()
"
pause
