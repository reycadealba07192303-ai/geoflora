from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image


def perceptual_hash(path: Path) -> int:
    with Image.open(path) as image:
        pixels = list(image.convert("L").resize((32, 32), Image.Resampling.LANCZOS).getdata())

    horizontal_cosines = [
        [
            math.cos((2 * x + 1) * frequency * math.pi / 64)
            for x in range(32)
        ]
        for frequency in range(8)
    ]
    vertical_cosines = [
        [
            math.cos((2 * y + 1) * frequency * math.pi / 64)
            for y in range(32)
        ]
        for frequency in range(8)
    ]
    coefficients: list[float] = []
    for vertical in range(8):
        for horizontal in range(8):
            coefficient = 0.0
            for y in range(32):
                vertical_cosine = vertical_cosines[vertical][y]
                for x in range(32):
                    coefficient += (
                        pixels[y * 32 + x]
                        * horizontal_cosines[horizontal][x]
                        * vertical_cosine
                    )
            if vertical == 0:
                coefficient *= math.sqrt(1 / 32)
            else:
                coefficient *= math.sqrt(2 / 32)
            if horizontal == 0:
                coefficient *= math.sqrt(1 / 32)
            else:
                coefficient *= math.sqrt(2 / 32)
            coefficients.append(coefficient)

    median = sorted(coefficients[1:])[len(coefficients[1:]) // 2]
    return sum(
        1 << index
        for index, coefficient in enumerate(coefficients)
        if coefficient > median
    )


def group_near_duplicates(
    records: list[dict[str, Any]],
    data_dir: Path,
    max_distance: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hashes = [
        perceptual_hash((data_dir / record["local_path"]).resolve())
        for record in records
    ]
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left_index, (left_record, left_hash) in enumerate(zip(records, hashes)):
        for right_index in range(left_index + 1, len(records)):
            right_record = records[right_index]
            if left_record["species_id"] != right_record["species_id"]:
                continue
            if (left_hash ^ hashes[right_index]).bit_count() <= max_distance:
                union(left_index, right_index)

    members: dict[int, list[int]] = {}
    for index in range(len(records)):
        members.setdefault(find(index), []).append(index)

    groups = [indices for indices in members.values() if len(indices) > 1]
    output_records = [dict(record) for record in records]
    reports: list[dict[str, Any]] = []
    grouped_indices: set[int] = set()
    for group_number, indices in enumerate(
        sorted(groups, key=lambda group: min(group)), start=1
    ):
        group_id = f"near-duplicate:{group_number:05d}"
        for index in indices:
            output_records[index]["near_duplicate_group_id"] = group_id
            grouped_indices.add(index)
        reports.append(
            {
                "group_id": group_id,
                "species_id": records[indices[0]]["species_id"],
                "count": len(indices),
                "source_ids": [records[index]["source_id"] for index in indices],
                "record_keys": [
                    {
                        "source": records[index].get("source"),
                        "source_id": records[index].get("source_id"),
                    }
                    for index in indices
                ],
            }
        )
    for index, record in enumerate(output_records):
        if index not in grouped_indices:
            record["near_duplicate_group_id"] = f"unique:{index:08d}"
    return output_records, reports
