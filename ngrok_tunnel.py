import sys, os, time, threading, webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyngrok import ngrok, conf

conf.get_default().auth_token = "3GdbZmVSvDUDCyAc5tvM8TymQkO_7snfP65arx8SAV2L1HXEQ"

tunnel = ngrok.connect(8000, "http")
url = tunnel.public_url

DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(DIR, "url_publica.txt"), "w") as f:
    f.write(url)

print("\n=== NGORK TUNNEL ATIVO ===")
print(f"URL PUBLICA: {url}/")
print(f"ADMIN:       {url}/admin")
print("==========================\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nParando tunnel...")
    ngrok.kill()
