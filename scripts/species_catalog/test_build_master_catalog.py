from __future__ import annotations

import unittest

from build_master_catalog import build_catalog


class BuildMasterCatalogTests(unittest.TestCase):
    def test_merges_exact_accepted_names_and_keeps_ecology_unverified(self):
        rows = [
            {
                "kind": "gbif_species_list",
                "stem": "gbif",
                "row": {
                    "accepted_taxon_key": "123",
                    "accepted_scientific_name": "Lantana camara L.",
                    "source_scientific_names": '["Lantana camara L."]',
                    "family": "Verbenaceae",
                    "genus": "Lantana",
                },
            },
            {
                "kind": "griis",
                "stem": "griis",
                "row": {
                    "gbif_backbone_key": "123",
                    "scientific_name": "Lantana camara",
                    "canonical_name": "Lantana camara",
                    "accepted_name": "Lantana camara L.",
                    "taxonomic_status": "ACCEPTED",
                },
            },
            {
                "kind": "malnaf",
                "stem": "malnaf",
                "row": {
                    "accepted_binomial": "Lantana camara",
                    "ecological_status": "naturalized",
                    "original_source_statuses": '["invasive", "naturalized"]',
                },
            },
        ]
        catalog = build_catalog(rows)
        self.assertEqual(len(catalog), 1)
        species = catalog[0]
        self.assertEqual(species["source_count"], 3)
        self.assertEqual(species["ecological_status_bucket"], "conflicting_source_claims_review_required")
        self.assertFalse(species["ecological_status_verified"])
        self.assertFalse(species["ai_model_supported"])
        self.assertEqual(species["catalog_review_status"], "pending_source_taxonomy_and_ecological_review")

    def test_griis_membership_does_not_claim_specific_invasive_status(self):
        catalog = build_catalog([{
            "kind": "griis",
            "stem": "griis",
            "row": {"gbif_backbone_key": "999", "scientific_name": "Testus plantus", "accepted_name": "Testus plantus", "taxonomic_status": "ACCEPTED"},
        }])
        self.assertEqual(catalog[0]["ecological_status_bucket"], "griis_introduced_or_invasive_membership_status_unspecified")
        self.assertFalse(catalog[0]["ecological_status_verified"])

    def test_absence_of_ecological_evidence_stays_unknown(self):
        catalog = build_catalog([{
            "kind": "gbif_species_list",
            "stem": "gbif",
            "row": {"accepted_taxon_key": "321", "accepted_scientific_name": "Examplea floribunda", "source_scientific_names": "[]"},
        }])
        self.assertEqual(catalog[0]["ecological_status_bucket"], "unknown_or_insufficiently_documented")

    def test_conflicting_gbif_keys_are_not_silently_joined(self):
        rows = [
            {"kind": "gbif_species_list", "stem": "gbif", "row": {"accepted_taxon_key": "111", "accepted_scientific_name": "Ambigua plantus A.", "source_scientific_names": "[]"}},
            {"kind": "gbif_species_list", "stem": "gbif", "row": {"accepted_taxon_key": "222", "accepted_scientific_name": "Ambigua plantus B.", "source_scientific_names": "[]"}},
            {"kind": "griis", "stem": "griis", "row": {"gbif_backbone_key": "333", "accepted_name": "Ambigua plantus", "scientific_name": "Ambigua plantus", "taxonomic_status": "ACCEPTED"}},
        ]
        unresolved = []
        catalog = build_catalog(rows, unresolved)
        self.assertEqual(len(catalog), 2)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "ambiguous_canonical_name_matches_multiple_gbif_taxon_keys")


if __name__ == "__main__":
    unittest.main()
