import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(DIR, 'mobilador.db')}")
os.environ.setdefault("SECRET_KEY", "M0b1l4d0rS3cr3tK3y!2024#SuperS3cur3")

from main import app

application = app
