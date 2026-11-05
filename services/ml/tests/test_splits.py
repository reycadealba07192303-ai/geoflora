import unittest

from geoflora_ml.datasets.split import assign_group_splits


class SplitTests(unittest.TestCase):
    def _records(self) -> list[dict[str, str]]:
        return [
            {"species_id": "species_a", "group_id": f"group-{index}", "source_id": str(index)}
            for index in range(10)
        ]

    def test_is_reproducible_and_never_splits_a_group(self) -> None:
        first = assign_group_splits(self._records(), seed=17)
        second = assign_group_splits(self._records(), seed=17)
        self.assertEqual(first, second)
        splits_by_group: dict[str, set[str]] = {}
        for record in first:
            splits_by_group.setdefault(record["group_id"], set()).add(record["split"])
        self.assertTrue(all(len(splits) == 1 for splits in splits_by_group.values()))
        self.assertEqual(
            {record["split"] for record in first}, {"train", "validation", "test"}
        )

    def test_requires_three_independent_groups_per_species(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 3"):
            assign_group_splits(self._records()[:2], seed=42)

    def test_near_duplicate_groups_never_cross_splits(self) -> None:
        records = self._records()
        records[0]["near_duplicate_group_id"] = "near:shared"
        records[5]["near_duplicate_group_id"] = "near:shared"
        assigned = assign_group_splits(records, seed=17)
        splits = {
            row["split"]
            for row in assigned
            if row.get("near_duplicate_group_id") == "near:shared"
        }
        self.assertEqual(len(splits), 1)
