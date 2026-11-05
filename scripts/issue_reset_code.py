"""Issue a one-time GeoFlora password reset code from the machine running the local database.

Recovery fallback when no administrator can sign in. Requires local machine access, which is the
trust boundary for this workspace. The code is printed once; only its SHA-256 hash is stored, it
expires after 30 minutes, and using it signs the account out everywhere.

    services/ml/.venv/Scripts/python.exe scripts/issue_reset_code.py <username>
"""
import argparse
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

URI = os.environ.get("GEOFLORA_MONGODB_URI", "mongodb://127.0.0.1:27017/geoflora")
MINUTES = 30  # Matches RESET_CODE_MINUTES in apps/web/src/lib/auth.ts.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    if not re.match(r"^mongodb://(127\.0\.0\.1|localhost)(:\d+)?/", URI):
        raise SystemExit("Only a local MongoDB database is supported.")
    database = MongoClient(URI, serverSelectionTimeoutMS=3000).get_default_database()
    user = database.accounts.find_one({"username": args.username.strip().lower()})
    if not user:
        raise SystemExit("No account with that username.")
    if user.get("disabled"):
        raise SystemExit("That account is disabled; enable it before issuing a reset code.")
    code = secrets.token_hex(6).upper()
    database.passwordresets.delete_many({"userId": user["_id"]})
    database.passwordresets.insert_one({"userId": user["_id"], "codeHash": hashlib.sha256(code.encode()).hexdigest(),
                                        "issuedBy": "local-cli", "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=MINUTES)})
    print(f"Reset code for {user['username']} ({user['role']}): {'-'.join(code[i:i + 4] for i in range(0, 12, 4))}")
    print(f"Use it on the sign-in screen under 'Forgot your password?' within {MINUTES} minutes.")


if __name__ == "__main__":
    main()
