"""Part 11 usability-study recorder checks through real HTTP on an isolated database (build apps/web first).

Starts a temporary `next start` on 5174 against geoflora_study_validation with synthetic sessions only.
Covers admin-only access, required consent, code/answer validation, server-side SUS scoring, summary
against targets, CSV export and participant withdrawal.
"""
import json
import os
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
URI = "mongodb://127.0.0.1:27017/geoflora_study_validation"
BASE = "http://127.0.0.1:5174"
CONSENT = "geoflora-usability-consent-v1-2026-10-27"
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("PASS", message)


def session_body(code, group="public", outcome="completed", sus=(5, 1, 5, 1, 5, 1, 5, 1, 5, 1), **changes):
    tasks = {"public": ["T1", "T2", "T3", "T4", "T5", "T7"], "researcher": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"], "environmental_officer": ["T1", "T2", "T3", "T4", "T6", "T7", "T8"]}[group]
    return {"participantCode": code, "group": group, "device": "Fixture laptop", "consent": True, "consentVersion": CONSENT, "sus": list(sus), "feedback": "Synthetic fixture",
            "tasks": [{"taskId": task, "outcome": outcome if task != "T2" else "assisted", "seconds": 40, "errors": 1 if task == "T3" else 0} for task in tasks], **changes}


def main():
    MongoClient(URI).drop_database("geoflora_study_validation")
    log = (ROOT / "storage/logs/study-smoke-web.log").open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env={**os.environ, "GEOFLORA_MONGODB_URI": URI}, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        admin, user = requests.Session(), requests.Session()
        assert admin.post(BASE + "/api/auth", json={"action": "setup", "username": "study_admin", "password": secrets.token_urlsafe(18)}, timeout=15).ok
        assert user.post(BASE + "/api/auth", json={"action": "register", "username": "study_user", "password": secrets.token_urlsafe(18)}, timeout=15).ok
        post = lambda body, session=admin: session.post(BASE + "/api/study", json=body, timeout=15)
        check(user.get(BASE + "/api/study", timeout=15).status_code == 403 and post(session_body("P01"), user).status_code == 403 and requests.get(BASE + "/api/study", timeout=15).status_code == 401, "only administrators can read or record study sessions")
        check(post(session_body("P01", consent=False)).status_code == 400 and post(session_body("P01", consentVersion="old")).status_code == 400, "a session cannot be saved without consent to the current script")
        check(post(session_body("Juan Dela Cruz")).status_code == 400, "participant codes must not be names")
        check(post(session_body("P01", sus=(5, 1, 5))).status_code == 400 and post(session_body("P01", sus=(6, 1, 5, 1, 5, 1, 5, 1, 5, 1))).status_code == 400, "all ten SUS answers from 1 to 5 are required")
        wrong_task = session_body("P01"); wrong_task["tasks"].append({"taskId": "T6", "outcome": "completed", "seconds": 10, "errors": 0})
        check(post(wrong_task).status_code == 400, "tasks outside the participant's group are rejected")
        response = post(session_body("P01"))
        check(response.status_code == 201 and response.json()["susScore"] == 100, "a valid session saves and the server computes SUS (all-positive answers = 100)")
        check(post(session_body("P01")).status_code == 409, "a participant code can only be used once")
        post(session_body("P02", "researcher", sus=(3, 3, 3, 3, 3, 3, 3, 3, 3, 3)))
        post(session_body("P03", "environmental_officer", outcome="failed", sus=(4, 2, 4, 2, 4, 2, 4, 2, 4, 2)))
        stored = MongoClient(URI).get_default_database().studysessions.find_one({"participantCode": "P01"})
        check(stored["consent"]["version"] == CONSENT and stored["consent"]["recordedBy"] == "study_admin" and stored["consent"]["givenAt"], "consent version, time and facilitator are stored with the session")
        summary = admin.get(BASE + "/api/study", timeout=15).json()["summary"]
        # Core T1-T4 per participant: P01 3/4 unassisted (T2 assisted), P02 3/4, P03 0/4 -> 6/12.
        check(summary["participants"] == 3 and summary["coreCompletion"] == 0.5 and summary["meanSus"] == (100 + 50 + 75) / 3, "summary computes core unassisted completion and mean SUS")
        check(summary["targets"] == {"participants": 10, "coreCompletion": 0.9, "sus": 70, "participantsMet": False, "coreCompletionMet": False, "susMet": True}, "summary compares results with the Part 1 targets")
        t2 = next(task for task in summary["perTask"] if task["taskId"] == "T2")
        check(t2["attempts"] == 3 and t2["unassistedCompletion"] == 0 and t2["medianSeconds"] is None, "assisted completions do not count as unassisted")
        csv = admin.get(BASE + "/api/study?format=csv", timeout=15)
        check(csv.headers["Content-Type"].startswith("text/csv") and csv.text.count("\r\n") == 6 + 8 + 7 and "Juan" not in csv.text, "CSV export has one row per task attempt and no names")
        check(admin.delete(BASE + "/api/study?participant=P02", timeout=15).status_code == 200 and admin.get(BASE + "/api/study", timeout=15).json()["summary"]["participants"] == 2, "withdrawing a participant deletes their session and updates the summary")
    finally:
        web.kill()
    (ROOT / "docs/part-11-study-recorder-smoke.json").write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": URI, "checks": checks}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
