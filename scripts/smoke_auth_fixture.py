"""Create legacy-style verified test accounts in an isolated smoke-test database.

Production registration now requires email verification. These HTTP workflow smokes
test report/access workflows, so seed accounts directly and never send real email.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import requests
from bson import ObjectId
from pymongo import MongoClient


def account(uri: str, username: str, role: str = "user"):
    password = "GeoFlora-Smoke-Only-2026"
    salt = secrets.token_hex(16)
    password_hash = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1, dklen=64).hex()
    user_id = ObjectId()
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    client = MongoClient(uri)
    db = client.get_database()
    db.accounts.insert_one({"_id": user_id, "username": username, "salt": salt, "passwordHash": password_hash,
                            "role": role, "createdAt": now, "updatedAt": now})
    db.sessions.insert_one({"tokenHash": hashlib.sha256(token.encode()).hexdigest(), "userId": user_id,
                            "expiresAt": now + timedelta(hours=8), "createdAt": now, "updatedAt": now})
    client.close()
    session = requests.Session()
    session.cookies.set("geoflora_session", token, domain="127.0.0.1", path="/")
    return session, str(user_id)
