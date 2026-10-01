"""Check the distinctions that matter for an empirical overlap audit."""

from __future__ import annotations

import unittest

from length_overlap import empirical_overlap, histogram_overlap, interval_intersection


class LengthOverlapTests(unittest.TestCase):
    """Protect boundary semantics and normalization against misleading overlap."""

    def test_disjoint_values_can_share_histogram_bin(self) -> None:
        """A bin must not be mistaken for exact or interval support overlap."""
        self.assertEqual(empirical_overlap([2670], [2678]), 0.0)
        self.assertFalse(interval_intersection((950, 2670), (2678, 5805))["overlaps_or_touches"])
        self.assertEqual(histogram_overlap([2670], [2678], 128, 6000), 1.0)

    def test_normalize_groups_independently(self) -> None:
        """Missing reasoning boundaries do not justify pooled denominators."""
        self.assertAlmostEqual(empirical_overlap([1, 1, 2, 2], [1, 1]), .5)
        self.assertEqual(empirical_overlap([1, 1], [1]), 1.0)

    def test_touching_intervals_are_explicit(self) -> None:
        """An endpoint shared by both observed ranges is retained."""
        result = interval_intersection((100, 200), (200, 300))
        self.assertTrue(result["overlaps_or_touches"])
        self.assertEqual(result["span_tokens"], 0)

    def test_output_cap_is_not_dropped_from_histogram(self) -> None:
        """The final common bin retains observations at exactly 6,000 tokens."""
        self.assertEqual(histogram_overlap([6000], [6000], 64, 6000), 1.0)


if __name__ == "__main__":
    unittest.main()
