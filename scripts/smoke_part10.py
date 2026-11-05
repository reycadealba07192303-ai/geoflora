"""Part 10 map/analytics checks: API results compared with independent queries over the stored records.

Starts a temporary `next start` on 5174 against geoflora_part10_validation and inserts synthetic report
documents (no photos) spanning species, statuses, owners, months, Manila-midnight boundaries and grid cells.
Every count the API returns is recomputed here from the database documents. Live data is untouched.
"""
import json
import math
import os
import secrets
import subprocess
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bson import ObjectId
from pymongo import MongoClient
from smoke_auth_fixture import account as fixture_account

ROOT = Path(__file__).resolve().parents[1]
URI = "mongodb://127.0.0.1:27017/geoflora_part10_validation"
BASE = "http://127.0.0.1:5174"
OUTPUT = ROOT / "docs/part-10-map-analytics-smoke.json"
MANILA = timezone(timedelta(hours=8))
CELL, MIN_CELL, HOTSPOT, SPARSE = 0.1, 3, 5, 20
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("PASS", message)


def account(action, username):
    return fixture_account(URI, username, "admin" if action == "setup" else "user")


def report(owner, status, species, lat, lng, observed, verified=True):
    doc = {"_id": ObjectId(), "ownerId": owner, "requestId": str(uuid.uuid4()), "payloadHash": uuid.uuid4().hex, "reportedSpecies": species if not verified else "unknown",
           "status": status, "observedAt": observed, "submittedAt": observed + timedelta(hours=1), "location": {"type": "Point", "coordinates": [lng, lat]},
           "locationMethod": "gps", "placeName": "fixture", "reviewHistory": [], "editHistory": [], "trainingConsent": False, "trainingCandidateStatus": "not_requested", "labelReviewStatus": "not_required"}
    if status == "verified" and verified:
        doc.update(verifiedScientificName=species, verifiedSpeciesId=species.lower().replace(" ", "_"), verifiedEcologicalStatus="target_invasive", verifiedRole="invasive")
    return doc


def seed(db, alice, bob):
    base = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)
    docs = []
    # Cell A (dense, hotspot): 8 verified Lantana/Chromolaena across owners and three months.
    for i in range(8):
        docs.append(report(alice if i % 2 else bob, "verified", "Lantana camara" if i < 5 else "Chromolaena odorata", 14.61 + i * 0.005, 121.01 + i * 0.004, base + timedelta(days=20 * (i % 3))))
    # Cell B: exactly 3 verified (shown, not a hotspot).
    for i in range(3):
        docs.append(report(bob, "verified", "Pontederia crassipes", 10.31 + i * 0.01, 123.88 + i * 0.01, base + timedelta(days=40)))
    # Cell C: 2 verified (suppressed in analytics, still exact on the owners' maps).
    docs.append(report(alice, "verified", "Lantana camara", 7.07, 125.61, base + timedelta(days=5)))
    docs.append(report(bob, "verified", "Lantana camara", 7.08, 125.62, base + timedelta(days=6)))
    # Manila-midnight boundary: 2026-09-30 16:30 UTC is 2026-10-01 00:30 in Manila.
    docs.append(report(alice, "verified", "Chromolaena odorata", 14.62, 121.02, datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc)))
    non_target = report(alice, "verified", "Euphorbia hirta", 14.615, 121.015, base + timedelta(days=10))
    non_target["verifiedEcologicalStatus"] = "non_target"; non_target["verifiedRole"] = "lookalike"; docs.append(non_target)
    # Unverified and excluded states.
    docs.append(report(alice, "pending", "Mikania micrantha", 14.63, 121.03, base + timedelta(days=1), verified=False))
    docs.append(report(alice, "correction_requested", "unknown", 14.64, 121.04, base + timedelta(days=2), verified=False))
    docs.append(report(bob, "pending", "Lantana camara", 10.32, 123.89, base + timedelta(days=3), verified=False))
    docs.append(report(alice, "rejected", "Lantana camara", 14.65, 121.05, base + timedelta(days=4), verified=False))
    withdrawn = report(alice, "withdrawn", "withdrawn", 14.66, 121.06, base, verified=False); withdrawn.pop("location"); docs.append(withdrawn)
    db.sightings.insert_many(docs)
    return docs


def manila_day(value, end=False):
    day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=MANILA)
    return (day + timedelta(days=1) - timedelta(microseconds=1000)) if end else day


def name(doc):
    return doc.get("verifiedScientificName") or doc["reportedSpecies"]


def expected(docs, layer="verified", owner=None, species="", start=None, end=None, bbox=None):
    rows = []
    for doc in docs:
        included = doc["status"] == "verified" and doc.get("verifiedEcologicalStatus") == "target_invasive"
        if layer != "verified" and doc["status"] in {"pending", "correction_requested"}:
            included = True
        if not included or (owner and doc["ownerId"] != owner) or "location" not in doc:
            continue
        observed = doc["observedAt"]
        lng, lat = doc["location"]["coordinates"]
        if species and not (name(doc).lower() == species or name(doc).lower().startswith(species + " ")):
            continue
        if (start and observed < manila_day(start)) or (end and observed > manila_day(end, True)):
            continue
        if bbox and not (bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        rows.append(doc)
    return rows


def aggregates(rows):
    cells = defaultdict(lambda: {"n": 0, "species": set()})
    for doc in rows:
        lng, lat = doc["location"]["coordinates"]
        key = (math.floor(lat / CELL), math.floor(lng / CELL))
        cells[key]["n"] += 1; cells[key]["species"].add(name(doc))
    shown = {key: value for key, value in cells.items() if value["n"] >= MIN_CELL}
    return {"total": len(rows), "bySpecies": Counter(name(doc) for doc in rows),
            "byMonth": Counter(doc["observedAt"].astimezone(MANILA).strftime("%Y-%m") for doc in rows),
            "cells": {(round(k[0] * CELL, 3), round(k[1] * CELL, 3)): (v["n"], len(v["species"])) for k, v in shown.items()},
            "suppressed": (len(cells) - len(shown), sum(v["n"] for k, v in cells.items() if k not in shown))}


def compare(api, rows, message):
    want = aggregates(rows)
    got_cells = {(cell["south"], cell["west"]): (cell["reports"], cell["species"]) for cell in api["cells"]}
    check(api["total"] == want["total"] and {r["species"]: r["reports"] for r in api["bySpecies"]} == dict(want["bySpecies"])
          and {r["month"]: r["reports"] for r in api["byMonth"]} == dict(want["byMonth"]) and got_cells == want["cells"]
          and (api["suppressed"]["cells"], api["suppressed"]["reports"]) == want["suppressed"]
          and [c["reports"] for c in api["hotspots"]] == sorted([n for n, _ in want["cells"].values() if n >= HOTSPOT], reverse=True)
          and api["sparse"] == (want["total"] < SPARSE), message)


def main():
    MongoClient(URI).drop_database("geoflora_part10_validation")
    db = MongoClient(URI).get_default_database()
    env = {**os.environ, "GEOFLORA_MONGODB_URI": URI, "GEOFLORA_ML_API_URL": "http://127.0.0.1:8000"}
    log = (ROOT / "storage/logs/part10-smoke-web.log").open("w", encoding="utf-8")
    web = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "5174"], cwd=ROOT / "apps/web", env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                requests.get(BASE + "/api/auth", timeout=3); break
            except requests.ConnectionError:
                time.sleep(0.5)
        admin, _ = account("setup", "fixture_admin")
        alice, alice_id = account("register", "alice_map")
        _, bob_id = account("register", "bob_map")
        rita, rita_id = account("register", "rita_map")
        admin.patch(BASE + "/api/accounts", json={"id": rita_id, "action": "set-role", "role": "reviewer"}, timeout=15)
        docs = seed(db, alice_id, bob_id)
        non_target_id = next(str(doc["_id"]) for doc in docs if doc.get("verifiedEcologicalStatus") == "non_target")
        get = lambda session, path: session.get(BASE + path, timeout=30)
        ids = lambda rows: sorted(str(doc["_id"]) for doc in rows)

        # Map points: visibility, layers, exact coordinates.
        check(get(requests.Session(), "/api/occurrences").status_code == 401 and get(requests.Session(), "/api/analytics").status_code == 401, "map and analytics require sign-in")
        points = get(alice, "/api/occurrences").json()
        check(points["scope"] == "mine" and sorted(p["id"] for p in points["points"]) == ids(expected(docs, owner=alice_id)), "contributor map shows only their own verified reports by default")
        stored = {str(doc["_id"]): doc for doc in docs}
        check(all([p["longitude"], p["latitude"]] == stored[p["id"]]["location"]["coordinates"] and p["species"] == name(stored[p["id"]]) for p in points["points"]), "map coordinates and species match the stored records exactly")
        check(all(p["id"] != non_target_id for p in points["points"]), "verified non-target plant is excluded from confirmed invasive map points")
        points = get(alice, "/api/occurrences?layer=all").json()["points"]
        check(sorted(p["id"] for p in points) == ids(expected(docs, "all", alice_id)) and {p["status"] for p in points} == {"verified", "pending", "correction_requested"}, "contributor pending layer adds their pending and correction-requested reports, never rejected or withdrawn")
        check(sorted(p["id"] for p in get(rita, "/api/occurrences").json()["points"]) == ids(expected(docs)), "reviewer map shows every verified workspace report")
        query = "species=lantana%20camara&from=2026-08-01&to=2026-08-31&bbox=120.9,14.5,121.2,14.8"
        check(sorted(p["id"] for p in get(rita, f"/api/occurrences?{query}").json()["points"]) == ids(expected(docs, species="lantana camara", start="2026-08-01", end="2026-08-31", bbox=(120.9, 14.5, 121.2, 14.8))), "species, date and area filters combine correctly on the map")
        boundary = get(rita, "/api/occurrences?from=2026-10-01&to=2026-10-01").json()["points"]
        check([p["observedAt"] for p in boundary] == ["2026-09-30T16:30:00.000Z"], "date filters use Philippine days (00:30 Manila on 1 October counts as 1 October)")

        # Analytics agree with independent recomputation.
        workspace = get(alice, "/api/analytics").json()
        compare(workspace, expected(docs), "workspace analytics totals, species, months, cells, suppression and hotspots match the database")
        check(all(row["species"] != "Euphorbia hirta" for row in workspace["bySpecies"]), "verified non-target plant is excluded from confirmed invasive analytics and hotspot counts")
        check(workspace["byMonth"][-1] == {"month": "2026-10", "reports": 1}, "month buckets use Philippine time")
        check(all(set(cell) == {"south", "west", "north", "east", "centerLat", "centerLng", "reports", "species"} for cell in workspace["cells"]) and "points" not in workspace and "ownerId" not in json.dumps(workspace), "analytics expose only generalized cells: no report IDs, owners or exact coordinates")
        check(workspace["suppressed"] == {"cells": 1, "reports": 2} and len(workspace["hotspots"]) == 1 and workspace["hotspots"][0]["reports"] >= HOTSPOT, "a 2-report cell is suppressed and only the dense cell is a hotspot")
        check(get(alice, "/api/analytics?layer=all").status_code == 400, "contributors cannot add other people's unverified reports to workspace analytics")
        compare(get(alice, "/api/analytics?scope=mine&layer=all").json(), expected(docs, "all", alice_id), "contributor's own analytics with the pending layer match the database")
        reviewer_all = get(rita, "/api/analytics?layer=all").json()
        compare(reviewer_all, expected(docs, "all"), "reviewer analytics with the pending layer match the database")
        check(reviewer_all["byStatus"] == dict(Counter(doc["status"] for doc in expected(docs, "all"))), "analytics report the status mix of the included layer")
        compare(get(rita, f"/api/analytics?{query}").json(), expected(docs, species="lantana camara", start="2026-08-01", end="2026-08-31", bbox=(120.9, 14.5, 121.2, 14.8)), "combined filters give matching analytics")
        options = get(alice, "/api/analytics").json()["speciesOptions"]
        check(options == sorted({name(doc) for doc in expected(docs)}), "species filter options list the species present in the layer")

        # Empty, sparse and invalid inputs.
        empty = get(alice, "/api/analytics?species=nonexistent%20plant").json()
        check(empty["total"] == 0 and empty["cells"] == [] and empty["bySpecies"] == [] and empty["sparse"], "a filter with no matches returns empty, sparse-flagged analytics")
        check(get(alice, "/api/occurrences?species=nonexistent%20plant").json()["points"] == [], "a filter with no matches returns no map points")
        for bad in ("from=2026-10-05&to=2026-10-01", "from=yesterday", "bbox=1,2,3", "bbox=121,15,120,14"):
            check(get(alice, f"/api/analytics?{bad}").status_code == 400 and get(alice, f"/api/occurrences?{bad}").status_code == 400, f"invalid filter rejected: {bad}")
    finally:
        web.kill()
    OUTPUT.write_text(json.dumps({"checkedAt": datetime.now(timezone.utc).isoformat(), "database": URI, "seededReports": 20, "checks": checks}, indent=2), encoding="utf-8")
    print(f"{len(checks)} checks passed")


if __name__ == "__main__":
    main()
