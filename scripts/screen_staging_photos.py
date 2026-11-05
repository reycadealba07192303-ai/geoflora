"""AI screen of staging photos: keep clear field photos of the target plant, drop the rest.

Each unscreened photo (pending, or accepted on its research-grade label) in
storage/datasets/staging/<role>_<group>_ph/review_queue.csv goes to the OpenRouter vision model
used by the web app (key from OPENROUTER_API_KEY or apps/web/.env.local). It is approved only when the model says it
is a field photograph (not a herbarium sheet, drawing or screenshot) that clearly shows the target plant, usable for
training, with confidence >= 0.8. Decisions are written back to the queue with the model name and rationale, so a
person can overrule any of them. Free models are rate-limited: the run stops on repeated 429s and resumes later.

Usage: python scripts/screen_staging_photos.py <group> [--limit 40]
"""
import argparse
import base64
import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image
from geoflora_ml.env import load_env

load_env()

ROOT = Path(__file__).resolve().parents[1]
MODELS = os.environ.get("GEOFLORA_AI_REVIEW_MODELS", "nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free").split(",")
APPROVE_MIN = 0.8
SCHEMA = {
    "type": "object",
    "properties": {
        "field_photo": {"type": "boolean", "description": "A real photograph of a living plant where it grows; false for herbarium sheets, pressed specimens, drawings, maps or screenshots."},
        "shows_target": {"type": "boolean", "description": "The main subject is clearly the target plant."},
        "usable": {"type": "boolean", "description": "In focus and the plant is large enough to learn its look."},
        "confidence": {"type": "number", "description": "Confidence in the three answers, 0 to 1."},
        "rationale": {"type": "string", "description": "One short sentence."},
    },
    "required": ["field_photo", "shows_target", "usable", "confidence", "rationale"],
    "additionalProperties": False,
}


def api_key():
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("Add OPENROUTER_API_KEY to apps/web/.env.local")
    return os.environ["OPENROUTER_API_KEY"]


def encode(path: Path):
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((1024, 1024))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def ask(key, label, image):
    body = json.dumps({
        "models": MODELS, "max_tokens": 1500, "provider": {"require_parameters": True},
        "response_format": {"type": "json_schema", "json_schema": {"name": "training_photo_screen", "strict": True, "schema": SCHEMA}},
        "messages": [
            {"role": "system", "content": f"You screen photos for a plant identification training set. The target plant is {label}. Judge only what is visible."},
            {"role": "user", "content": [{"type": "text", "text": f"Is this a usable field photo of {label}?"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}]},
        ],
    }).encode()
    request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "GeoFlora training screen"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read())
    content = (payload["choices"][0]["message"].get("content") or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return payload.get("model", MODELS[0]), json.loads(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("group")
    # A small default leaves most of the free daily allowance (50 requests) for the sighting reviewer and suggestions.
    parser.add_argument("--limit", type=int, default=15, help="most photos to screen in this run")
    args = parser.parse_args()
    data = next((ROOT / "storage/datasets/staging").glob(f"*_{args.group}_ph"))
    label = json.loads((data / "group.json").read_text(encoding="utf-8"))["label"]
    queue = data / "review_queue.csv"
    with queue.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    key, done, throttled = api_key(), 0, 0
    # Unlabelled photos first (they cannot be trained until screened), then research-grade ones (already usable).
    pending = sorted((row for row in rows if row["review_status"] in ("pending", "research_grade")), key=lambda row: (row["review_status"] != "pending", row["source"] != "inaturalist"))
    for row in pending[: args.limit]:
        try:
            model, answer = ask(key, label, encode(data / row["local_path"]))
        except urllib.error.HTTPError as error:
            if error.code == 429 and "per-day" in error.read().decode(errors="replace"):
                # The free daily allowance is shared with the sighting reviewer and plant suggestions; stop and leave it.
                reset = error.headers.get("X-RateLimit-Reset")
                print("Free daily AI allowance used up; stopping." + (f" Resets at {time.strftime('%Y-%m-%d %H:%M', time.localtime(int(reset) / 1000))}." if reset else ""))
                break
            if error.code == 429:
                throttled += 1
                if throttled >= 3:
                    print("Rate limited by the free tier; stopping. Run again later to continue.")
                    break
                time.sleep(30)
                continue
            print(f"{row['source_id']}: HTTP {error.code}; left pending")
            continue
        except (ValueError, KeyError, urllib.error.URLError) as error:
            print(f"{row['source_id']}: {error}; left pending")
            continue
        approved = bool(answer.get("field_photo") and answer.get("shows_target") and answer.get("usable")) and float(answer.get("confidence", 0)) >= APPROVE_MIN
        row.update(review_status="approved" if approved else "rejected", reviewer=f"ai:{model}", review_rationale=str(answer.get("rationale", ""))[:300])
        done += 1
        print(f"{row['review_status']:8} {row['source']:11} {row['source_id'][:40]}: {row['review_rationale']}")
        with queue.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        time.sleep(2)
    counts = {status: sum(row["review_status"] == status for row in rows) for status in ("approved", "rejected", "research_grade", "pending")}
    print(json.dumps({"screened_this_run": done, **counts}))


if __name__ == "__main__":
    main()
