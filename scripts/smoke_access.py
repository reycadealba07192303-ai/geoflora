"""Part 7 access-control checks through real HTTP on an isolated database (build apps/web first).

Starts a temporary `next start` on 5174 against geoflora_access_validation. Covers roles
(contributor/reviewer/administrator), server-side authorization, ownership boundaries, sessions,
logout, disabling, admin-issued and CLI reset codes, and password change. Live data is not touched.
"""
import io
import json
import os
import secrets
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
URI = "mongodb://127.0.0.1:27017/geoflora_access_validation"
BASE = "http://127.0.0.1:5174"
OUTPUT = ROOT / "docs/part-7-access-smoke.json"
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("PASS", message)


def status(response, expected, message):
    check(response.status_code == expected, f"{message} ({response.status_code})" if response.status_code == expected else f"{message}: expected {expected}, got {response.status_code} {response.text[:200]}")


def account(action, username, password):
    session = requests.Session()
    return session, session.post(BASE + "/api/auth", json={"action": action, "username": username, "password": password}, timeout=15)


def photo():
    buffer = io.BytesIO()
    Image.fromarray(np.random.default_rng().integers(0, 256, (160, 160, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def submit(session):
    fields = {"requestId": str(uuid.uuid4()), "species": "unknown", "plantDescription": "Broad leaves with small purple flowers near a canal.",
              "latitude": "14.5995", "longitude": "120.9842", "locationMethod": "manual", "placeName": "Isolated access test",
              "observedAt": datetime.now(timezone.utc).isoformat(), "consent": "yes"}
    return session.post(BASE + "/api/sightings", data=fields, files={"image": ("plant.png", photo(), "image/png")}, timeout=30)


def main():
    MongoClient(URI).drop_database("geoflora_access_validation")
    env = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_ML_API_URL": "http://127.0.0.1:8999"}
    log = (ROOT / "storage/logs/access-smoke-web.log").open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        pw = {name: secrets.token_urlsafe(18) for name in ("admin", "alice", "bob", "rita")}
        admin, response = account("setup", "fixture_admin", pw["admin"])
        status(response, 200, "first administrator setup")
        cookie = response.headers.get("set-cookie", "")
        check("HttpOnly" in cookie and "SameSite=strict" in cookie.replace("Strict", "strict"), "session cookie is HttpOnly and SameSite=Strict")
        status(account("setup", "second_admin", pw["admin"])[1], 409, "second setup is refused once an administrator exists")
        alice, response = account("register", "alice_contrib", pw["alice"])
        check(response.status_code == 200 and response.json()["user"]["role"] == "user", "public registration creates a contributor")
        bob, _ = account("register", "bob_contrib", pw["bob"])
        rita, response = account("register", "rita_reviewer", pw["rita"])
        rita_id = response.json()["user"]["id"]
        sneaky = requests.Session()
        response = sneaky.post(BASE + "/api/auth", json={"action": "register", "username": "sneaky_admin", "password": pw["bob"], "role": "admin"}, timeout=15)
        check(response.json()["user"]["role"] == "user", "a registration cannot request a privileged role")

        # Contributor boundaries.
        for method, path, body in (("get", "/api/accounts", None), ("patch", "/api/accounts", {"id": rita_id, "action": "set-role", "role": "admin"}),
                                   ("get", "/api/admin/review", None), ("patch", "/api/admin/review", {"id": "0" * 24, "action": "reject", "rationale": "x"}),
                                   ("get", "/api/sightings?trainingCandidates=1", None)):
            status(getattr(alice, method)(BASE + path, json=body, timeout=15), 403, f"contributor is refused {method.upper()} {path}")
        status(requests.get(BASE + "/api/accounts", timeout=15), 401, "signed-out request to accounts is refused")
        status(admin.get(BASE + "/api/accounts", headers={"Origin": "http://evil.example"}, timeout=15), 403, "cross-origin administrator request is refused")

        response = submit(alice)
        status(response, 201, "contributor submits a pending report")
        report = response.json()["id"]
        for suffix in ("", "/photo", "/pdf"):
            status(bob.get(BASE + f"/api/sightings/{report}{suffix}", timeout=30), 404, f"another contributor cannot read the report{suffix or ' detail'}")
            status(requests.get(BASE + f"/api/sightings/{report}{suffix}", timeout=30), 401, f"signed-out request cannot read the report{suffix or ' detail'}")
        check(all(row["id"] != report for row in bob.get(BASE + "/api/sightings", timeout=15).json()["reports"]), "another contributor's list excludes the report")
        status(alice.get(BASE + f"/api/sightings/{report}", timeout=15), 200, "owner reads their own report")

        # Reviewer role: moderation without administration.
        status(rita.get(BASE + "/api/admin/review", timeout=15), 403, "contributor cannot open the review queue before promotion")
        response = admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "reviewer"}, timeout=15)
        check(response.status_code == 200 and response.json()["role"] == "reviewer", "administrator promotes a contributor to reviewer")
        response = rita.get(BASE + "/api/admin/review", timeout=15)
        check(response.status_code == 200 and response.json()["role"] == "reviewer", "promotion applies to the existing reviewer session immediately")
        check(response.json()["jobs"] == [] and response.json()["worker"] is None, "reviewer queue omits training job and worker details")
        check(any(row["id"] == report for row in response.json()["reports"]), "reviewer sees the pending report in the queue")
        status(rita.get(BASE + f"/api/sightings/{report}/photo", timeout=15), 200, "reviewer can open the report photo for moderation")
        status(rita.get(BASE + "/api/accounts", timeout=15), 403, "reviewer cannot manage accounts")
        response = rita.patch(BASE + "/api/admin/review", json={"id": report, "action": "reject", "rationale": "Photo does not show identifying features."}, timeout=15)
        status(response, 200, "reviewer records a review decision")
        reviewed = admin.get(BASE + "/api/admin/review?view=rejected", timeout=15).json()
        history = next(row for row in reviewed["reports"] if row["id"] == report)["reviewHistory"]
        check(history[-1]["reviewer"] == "rita_reviewer" and history[-1]["action"] == "reject", "review history records the reviewer and action")
        status(rita.patch(BASE + "/api/admin/review", json={"id": report, "action": "reject", "rationale": "Again"}, timeout=15), 409, "a completed review cannot be repeated")
        admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "user"}, timeout=15)
        status(rita.get(BASE + "/api/admin/review", timeout=15), 403, "demotion removes review access immediately")

        # Administrator lockout protection.
        admin_id = admin.get(BASE + "/api/auth", timeout=15).json()["user"]["id"]
        status(admin.patch(BASE + "/api/accounts", json={"id": admin_id, "action": "set-role", "role": "user"}, timeout=15), 409, "administrator cannot demote themselves")
        status(admin.patch(BASE + "/api/accounts", json={"id": admin_id, "action": "disable"}, timeout=15), 409, "administrator cannot disable themselves")
        status(admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "owner"}, timeout=15), 400, "unknown roles are rejected")

        # Disabling revokes sessions and blocks sign-in.
        bob_id = bob.get(BASE + "/api/auth", timeout=15).json()["user"]["id"]
        admin.patch(BASE + "/api/accounts", json={"id": bob_id, "action": "disable"}, timeout=15)
        status(bob.get(BASE + "/api/sightings", timeout=15), 401, "disabled account's existing session stops working")
        status(account("login", "bob_contrib", pw["bob"])[1], 403, "disabled account cannot sign in")
        status(admin.patch(BASE + "/api/accounts", json={"id": bob_id, "action": "reset-code"}, timeout=15), 409, "reset codes are not issued to disabled accounts")
        admin.patch(BASE + "/api/accounts", json={"id": bob_id, "action": "enable"}, timeout=15)
        status(account("login", "bob_contrib", pw["bob"])[1], 200, "re-enabled account can sign in")

        # Admin-issued reset code.
        alice_id = alice.get(BASE + "/api/auth", timeout=15).json()["user"]["id"]
        code = admin.patch(BASE + "/api/accounts", json={"id": alice_id, "action": "reset-code"}, timeout=15).json()["code"]
        new_alice = secrets.token_urlsafe(18)
        reset = lambda c, p: requests.post(BASE + "/api/auth", json={"action": "reset", "username": "alice_contrib", "code": c, "password": p}, timeout=15)
        status(reset("AAAA-BBBB-CCCC", new_alice), 400, "a wrong reset code is refused")
        status(requests.post(BASE + "/api/auth", json={"action": "reset", "username": "nobody_here", "code": code, "password": new_alice}, timeout=15), 400, "reset for an unknown username gives the same refusal")
        status(reset(code.lower().replace("-", " "), new_alice), 200, "the issued code resets the password (case and separators ignored)")
        status(alice.get(BASE + "/api/sightings", timeout=15), 401, "password reset signs out existing sessions")
        status(reset(code, secrets.token_urlsafe(18)), 400, "a reset code works only once")
        status(account("login", "alice_contrib", pw["alice"])[1], 401, "the old password no longer works")
        alice, response = account("login", "alice_contrib", new_alice)
        status(response, 200, "the new password signs in")

        # Change password while signed in.
        laptop, _ = account("login", "alice_contrib", new_alice)
        change = lambda current, new: alice.post(BASE + "/api/auth", json={"action": "change-password", "currentPassword": current, "password": new}, timeout=15)
        status(change("wrong-password-123", secrets.token_urlsafe(18)), 401, "password change requires the current password")
        status(change(new_alice, new_alice), 400, "password change refuses reusing the current password")
        changed = secrets.token_urlsafe(18)
        status(change(new_alice, changed), 200, "contributor changes their password")
        status(alice.get(BASE + "/api/sightings", timeout=15), 200, "the session that changed the password stays signed in")
        status(laptop.get(BASE + "/api/sightings", timeout=15), 401, "other sessions are signed out after a password change")
        status(requests.post(BASE + "/api/auth", json={"action": "change-password", "currentPassword": changed, "password": secrets.token_urlsafe(18)}, timeout=15), 401, "signed-out password change is refused")

        # Local CLI recovery for administrators.
        result = subprocess.run([str(ROOT / "services/ml/.venv/Scripts/python.exe"), str(ROOT / "scripts/issue_reset_code.py"), "fixture_admin"],
                                env={**os.environ, "GEOFLORA_MONGODB_URI": URI}, capture_output=True, text=True, timeout=30, check=True)
        cli_code = result.stdout.split(": ")[1].split()[0]
        admin_password = secrets.token_urlsafe(18)
        response = requests.post(BASE + "/api/auth", json={"action": "reset", "username": "fixture_admin", "code": cli_code, "password": admin_password}, timeout=15)
        check(response.status_code == 200 and response.json()["user"]["role"] == "admin", "local CLI reset code recovers an administrator")
        status(admin.get(BASE + "/api/accounts", timeout=15), 401, "administrator's old session ends after CLI recovery")

        # Logout.
        admin, _ = account("login", "fixture_admin", admin_password)
        status(admin.delete(BASE + "/api/auth", timeout=15), 200, "logout succeeds")
        status(admin.get(BASE + "/api/accounts", timeout=15), 401, "the session is invalid after logout")
        stored = MongoClient(URI).get_default_database()
        check(stored.passwordresets.count_documents({}) == 0, "used reset codes are removed from the database")
    finally:
        web.kill()
    OUTPUT.write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": URI, "checks": checks}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
