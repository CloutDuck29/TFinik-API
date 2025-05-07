# config.py

from datetime import timedelta

# 🔐 JWT
SECRET = "supersecretkey"
ALGO = "HS256"
ACCESS_TTL = timedelta(days=30)
