"""Duplicate detection and observation grouping (the unit of train/val/test splitting).

Images end up in one group when any of these link them:
  * same observation (GBIF occurrence)
  * identical file bytes (SHA-256)
  * perceptual hash within the near-duplicate threshold
  * optionally, same species + same recorder + same day (likely the same plant patch)
A group that links images of different species is a label conflict and is excluded from training.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            self.parent[rb] = ra  # smallest id becomes root -> deterministic

    def groups(self) -> dict:
        return {x: self.find(x) for x in self.parent}


def _phash_to_uint64(h: str) -> np.uint64:
    return np.uint64(int(h, 16))


def _popcount64(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.uint64)
    x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
    x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
    x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return ((x * np.uint64(0x0101010101010101)) >> np.uint64(56)).astype(np.int64)


def near_duplicate_pairs(image_ids: list[str], phashes: list[str], threshold: int) -> list[tuple[str, str, int]]:
    """All pairs whose 64-bit perceptual hashes differ in <= threshold bits (vectorised, O(n^2/2))."""
    valid = [(i, h) for i, h in zip(image_ids, phashes) if h]
    if len(valid) < 2:
        return []
    ids = [i for i, _ in valid]
    arr = np.array([_phash_to_uint64(h) for _, h in valid], dtype=np.uint64)
    pairs = []
    for k in range(len(arr) - 1):
        d = _popcount64(np.bitwise_xor(arr[k + 1:], arr[k]))
        for j in np.nonzero(d <= threshold)[0]:
            pairs.append((ids[k], ids[k + 1 + j], int(d[j])))
    return pairs


def short_hash(text: str, n: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def compute_groups(df: pd.DataFrame, phash_threshold: int, group_by_recorder_and_date: bool) -> pd.DataFrame:
    """Return a frame indexed like df with exact_duplicate_of, near_duplicate_cluster,
    observation_group and label_conflict columns."""
    out = pd.DataFrame(index=df.index)
    ids = df["image_id"].tolist()
    id_to_species = dict(zip(df["image_id"], df["species_id"]))

    # exact duplicates: canonical = smallest image_id per hash
    exact_of = {}
    for _, grp in df[df["file_sha256"] != ""].groupby("file_sha256"):
        members = sorted(grp["image_id"])
        for m in members[1:]:
            exact_of[m] = members[0]
    out["exact_duplicate_of"] = df["image_id"].map(lambda i: exact_of.get(i, ""))

    # near-duplicate clusters
    nd = UnionFind(ids)
    readable = df[(df["phash"] != "")]
    for a, b, _ in near_duplicate_pairs(readable["image_id"].tolist(), readable["phash"].tolist(), phash_threshold):
        nd.union(a, b)
    nd_roots = nd.groups()
    cluster_sizes = pd.Series(list(nd_roots.values())).value_counts()
    out["near_duplicate_cluster"] = df["image_id"].map(
        lambda i: f"nd-{short_hash(nd_roots[i])}" if cluster_sizes.get(nd_roots[i], 0) > 1 else "")

    # observation groups = near-dup clusters + exact dups + same observation (+ recorder/day)
    uf = UnionFind(ids)
    for a, root in nd_roots.items():
        uf.union(a, root)
    for a, b in exact_of.items():
        uf.union(a, b)
    keys = [df["observation_id"]]
    if group_by_recorder_and_date:
        day = df["event_date"].str.slice(0, 10)
        rec = df["recorded_by"].str.strip().str.lower()
        visit = df["species_id"] + "|" + rec + "|" + day
        keys.append(visit.where((rec != "") & (day != ""), ""))
    for key_series in keys:
        for members in _nonempty_groups(df, key_series):
            for m in members[1:]:
                uf.union(members[0], m)
    roots = uf.groups()
    out["observation_group"] = df["image_id"].map(lambda i: f"grp-{short_hash(roots[i])}")

    species_per_group = out.assign(species=df["image_id"].map(id_to_species)).groupby("observation_group")["species"].nunique()
    conflicted = set(species_per_group[species_per_group > 1].index)
    out["label_conflict"] = out["observation_group"].map(lambda g: "true" if g in conflicted else "false")
    return out


def _nonempty_groups(df: pd.DataFrame, key_series: pd.Series):
    mask = key_series != ""
    for _, members in df.loc[mask, "image_id"].groupby(key_series[mask]):
        lst = sorted(members.tolist())
        if len(lst) > 1:
            yield lst
