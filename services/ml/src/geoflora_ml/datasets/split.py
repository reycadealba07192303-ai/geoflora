from __future__ import annotations

import random
from collections import defaultdict
from typing import Any


def assign_group_splits(
    records: list[dict[str, Any]],
    seed: int,
    ratios: tuple[float, float, float] = (0.7, 0.15, 0.15),
) -> list[dict[str, Any]]:
    if any(ratio <= 0 for ratio in ratios) or abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("Split ratios must be positive and sum to 1")

    parent = list(range(len(records)))
    group_owner: dict[str, int] = {}

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

    for index, record in enumerate(records):
        species_id = record.get("species_id")
        group_id = record.get("group_id")
        near_duplicate_group_id = record.get("near_duplicate_group_id")
        if not species_id or not group_id:
            raise ValueError("Every record must have a species_id and source group")
        for key in (f"source:{group_id}", f"near:{near_duplicate_group_id}"):
            if key.endswith("None"):
                continue
            if key in group_owner:
                union(index, group_owner[key])
            else:
                group_owner[key] = index

    rng = random.Random(seed)
    component_indices: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        component_indices[find(index)].append(index)
    components = list(component_indices.values())
    species_group_counts: dict[str, int] = defaultdict(int)
    for indices in components:
        for species_id in {str(records[index]["species_id"]) for index in indices}:
            species_group_counts[species_id] += 1
    insufficient = [
        species_id for species_id, count in species_group_counts.items() if count < 3
    ]
    if insufficient:
        raise ValueError(
            "at least 3 independent source/near-duplicate groups are required per "
            f"species; insufficient groups for: {', '.join(sorted(insufficient))}"
        )

    rng.shuffle(components)
    split_names = ("train", "validation", "test")
    totals: dict[str, int] = defaultdict(int)
    for record in records:
        totals[str(record["species_id"])] += 1
    targets = {
        species_id: [ratio * total for ratio in ratios]
        for species_id, total in totals.items()
    }
    counts: dict[str, list[int]] = {
        species_id: [0, 0, 0] for species_id in totals
    }
    remaining: dict[str, int] = dict(species_group_counts)
    component_assignments: dict[int, str] = {}

    for indices in components:
        component_species: dict[str, int] = defaultdict(int)
        for index in indices:
            component_species[str(records[index]["species_id"])] += 1
        must_fill = set()
        for species_id in component_species:
            empty = {i for i, count in enumerate(counts[species_id]) if count == 0}
            if remaining[species_id] == len(empty):
                must_fill.update(empty)
        possible = must_fill if must_fill else set(range(3))
        split_index = max(
            possible,
            key=lambda candidate: sum(
                (targets[species_id][candidate] - counts[species_id][candidate])
                / max(targets[species_id][candidate], 1)
                for species_id in component_species
            ),
        )
        component_key = min(indices)
        component_assignments[component_key] = split_names[split_index]
        for species_id, count in component_species.items():
            counts[species_id][split_index] += count
            remaining[species_id] -= 1

    assignments: list[dict[str, Any]] = []
    for indices in components:
        split_name = component_assignments[min(indices)]
        for index in indices:
            assignments.append({**records[index], "split": split_name})

    missing_splits = [
        species_id
        for species_id, split_counts in counts.items()
        if any(count == 0 for count in split_counts)
    ]
    if missing_splits:
        raise ValueError(
            "Unable to create train/validation/test partitions without group leakage "
            f"for: {', '.join(sorted(missing_splits))}"
        )
    return assignments
