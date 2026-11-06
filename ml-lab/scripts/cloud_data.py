"""Training photos for cloud training, kept in MongoDB Atlas (GridFS bucket "training_data").

The model trains on 224 x 224 crops, so the cloud copy stores every photo of the 21-class split
(dataset/nissap/{train,val,test,unknown_val,unknown_test}) at most 256 px on its longest side, packed in tar shards.
The bucket is private to the GeoFlora database (it is not public like the GitHub repository).

  python scripts/cloud_data.py upload            # pack dataset/nissap and upload it (replaces the stored copy)
  python scripts/cloud_data.py download          # restore dataset/nissap from the stored copy
  python scripts/cloud_data.py add PATH [...]    # upload extra photos (paths under dataset/nissap) as a new shard
  python scripts/cloud_data.py status
The Mongo URI comes from --mongo-uri, GEOFLORA_MONGODB_URI, or apps/web/.env.local.
"""
import argparse
import io
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
DATA = LAB / "dataset" / "nissap"
SPLITS = ("train", "val", "test", "unknown_val", "unknown_test")
MAX_SIDE, QUALITY, SHARD_BYTES = 256, 88, 40 * 1024 * 1024


def mongo_uri(arg):
    if arg:
        return arg
    if os.environ.get("GEOFLORA_MONGODB_URI"):
        return os.environ["GEOFLORA_MONGODB_URI"]
    env = LAB.parent / "apps" / "web" / ".env.local"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("GEOFLORA_MONGODB_URI="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Set GEOFLORA_MONGODB_URI")


def bucket(uri):
    import gridfs
    from pymongo import MongoClient
    db = MongoClient(uri, serverSelectionTimeoutMS=20000).get_default_database()
    return db, gridfs.GridFSBucket(db, bucket_name="training_data")


def compact(path: Path) -> bytes:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO(); im.save(buf, format="JPEG", quality=QUALITY, optimize=True)
        return buf.getvalue()


def write_shards(fs, files, prefix):
    shards, buf, tar, count = [], None, None, 0

    def flush():
        nonlocal buf, tar
        if tar is None:
            return
        tar.close()
        name = f"{prefix}-{len(shards):03d}.tar"
        fs.upload_from_stream(name, buf.getvalue(), metadata={"kind": "shard", "created": datetime.now(timezone.utc)})
        shards.append(name); print(f"  uploaded {name} ({buf.tell() / 1e6:.1f} MB)", flush=True)
        buf, tar = None, None

    for path in files:
        if tar is None:
            buf = io.BytesIO(); tar = tarfile.open(fileobj=buf, mode="w")
        data = compact(path)
        info = tarfile.TarInfo(path.relative_to(LAB).as_posix()); info.size = len(data)
        tar.addfile(info, io.BytesIO(data)); count += 1
        if buf.tell() >= SHARD_BYTES:
            flush()
    flush()
    return shards, count


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["upload", "download", "add", "status"])
    p.add_argument("paths", nargs="*")
    p.add_argument("--mongo-uri", default=None)
    args = p.parse_args()
    db, fs = bucket(mongo_uri(args.mongo_uri))
    shards = list(db["training_data.files"].find({"metadata.kind": "shard"}, {"filename": 1, "length": 1}).sort("filename", 1))
    if args.command == "status":
        print(f"{len(shards)} shard(s), {sum(s['length'] for s in shards) / 1e6:.1f} MB")
        for s in shards: print(" ", s["filename"], f"{s['length'] / 1e6:.1f} MB")
    elif args.command == "upload":
        files = sorted(f for split in SPLITS for f in (DATA / split).rglob("*") if f.is_file())
        print(f"packing {len(files)} photos (max {MAX_SIDE}px)", flush=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        new, count = write_shards(fs, files, f"base-{stamp}")
        for s in shards:  # replace the previous copy only after the new one is complete
            fs.delete(s["_id"])
        print(f"done: {count} photos in {len(new)} shard(s); removed {len(shards)} old shard(s)")
    elif args.command == "add":
        files = [Path(x).resolve() for x in args.paths]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        new, count = write_shards(fs, files, f"add-{stamp}")
        print(f"added {count} photo(s) in {len(new)} shard(s)")
    elif args.command == "download":
        total = 0
        for s in shards:
            stream = fs.open_download_stream(s["_id"])
            with tarfile.open(fileobj=io.BytesIO(stream.read()), mode="r") as tar:
                for member in tar.getmembers():
                    target = (LAB / member.name).resolve()
                    if not str(target).startswith(str(DATA.resolve())):
                        continue  # only files under dataset/nissap
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read()); total += 1
        print(f"restored {total} photos from {len(shards)} shard(s) into {DATA}")


if __name__ == "__main__":
    main()
