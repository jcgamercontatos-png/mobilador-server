import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join('/tmp', 'mobilador.db')}"
os.environ["VERCEL"] = "1"
from main import app
