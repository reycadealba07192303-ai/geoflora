import unittest

from geoflora_ml.collection.licensing import normalize_license, training_license_eligible


class LicenseTests(unittest.TestCase):
    def test_allows_permissive_creative_commons_licenses(self) -> None:
        self.assertEqual(normalize_license("cc0"), "cc0")
        self.assertEqual(normalize_license("CC-BY"), "cc-by")
        self.assertEqual(
            normalize_license("https://creativecommons.org/licenses/by-sa/4.0/"),
            "cc-by-sa",
        )

    def test_rejects_unknown_and_restricted_licenses(self) -> None:
        self.assertIsNone(normalize_license(None))
        self.assertIsNone(normalize_license("cc-by-nc"))
        self.assertIsNone(
            normalize_license("https://creativecommons.org/licenses/by-nc/4.0/")
        )

    def test_non_commercial_only_when_the_caller_opts_in(self) -> None:
        self.assertEqual(normalize_license("cc-by-nc", allow_noncommercial=True), "cc-by-nc")
        self.assertEqual(normalize_license("https://creativecommons.org/licenses/by-nc-sa/4.0/", allow_noncommercial=True), "cc-by-nc-sa")
        self.assertEqual(normalize_license("https://creativecommons.org/licenses/by-nc/3.0/", allow_noncommercial=True), "cc-by-nc")
        self.assertIsNone(normalize_license("cc-by-nc-nd", allow_noncommercial=True))
        self.assertIsNone(normalize_license("all rights reserved", allow_noncommercial=True))

    def test_training_allowlist_holds_noncommercial_and_requires_attribution(self) -> None:
        self.assertTrue(training_license_eligible("cc0"))
        self.assertTrue(training_license_eligible("cc-by", "Photographer"))
        self.assertFalse(training_license_eligible("cc-by", ""))
        self.assertFalse(training_license_eligible("cc-by-nc", "Photographer"))
        self.assertTrue(training_license_eligible("owner_own_photo", "Photographer"))
        self.assertFalse(training_license_eligible("owner_own_photo", ""))
