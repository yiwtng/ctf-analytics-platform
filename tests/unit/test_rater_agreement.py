"""Reliability statistics, checked against published reference values.

These coefficients decide whether the paper can claim its measure is reliable
(H2) and whether the RQ4 comparison is trustworthy. A silent arithmetic error
here would not fail anything else -- it would simply produce a plausible number
and change the paper's conclusion. Hence reference values from the literature
rather than self-generated expectations.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "research"))

from rater_agreement import cohen_kappa, icc_2k  # noqa: E402

FIVE = [1, 2, 3, 4, 5]


class TestCohenKappa:
    def test_matches_textbook_two_by_two(self):
        # 20 both-yes, 5 A-yes/B-no, 10 A-no/B-yes, 15 both-no.
        # po = .70, pe = .50, kappa = .40
        pairs = [(1, 1)] * 20 + [(1, 2)] * 5 + [(2, 1)] * 10 + [(2, 2)] * 15
        assert cohen_kappa(pairs, [1, 2]) == pytest.approx(0.40)

    def test_perfect_agreement_is_one(self):
        pairs = [(1, 1), (3, 3), (5, 5), (2, 2), (4, 4)]
        assert cohen_kappa(pairs, FIVE) == pytest.approx(1.0)
        assert cohen_kappa(pairs, FIVE, weighted=True) == pytest.approx(1.0)

    def test_constant_ratings_are_undefined_not_zero_or_one(self):
        # Both raters give 3 to everything. Agreement is total but carries no
        # information, and chance agreement is also total. Returning 0 would read
        # as "no better than chance"; returning 1 as "perfect". Both mislead.
        assert cohen_kappa([(3, 3)] * 10, FIVE) is None

    def test_quadratic_weighting_penalises_near_misses_less(self):
        near = [(4, 5)] * 10 + [(1, 1)] * 10
        far = [(1, 5)] * 10 + [(1, 1)] * 10
        assert (cohen_kappa(near, FIVE, weighted=True)
                > cohen_kappa(far, FIVE, weighted=True))

    def test_unweighted_ignores_how_far_apart_the_disagreement_is(self):
        # The two scenarios must have the SAME marginals, or the comparison says
        # nothing: kappa depends on the marginal distributions as well as on the
        # observed agreement, so two sets of pairs with equal exact-agreement can
        # legitimately differ in kappa. Symmetric off-diagonal pairs keep both
        # raters' marginals at 50/50 in each scenario.
        adjacent = [(1, 2)] * 10 + [(2, 1)] * 10   # every disagreement 1 apart
        extreme = [(1, 5)] * 10 + [(5, 1)] * 10    # every disagreement 4 apart
        assert cohen_kappa(adjacent, FIVE) == pytest.approx(cohen_kappa(extreme, FIVE))

    def test_weighted_exceeds_unweighted_when_misses_are_adjacent(self):
        # The practically important property, and the reason the
        # pre-registration reports the weighted coefficient for an ordered 1-5
        # scale: raters who mostly agree and are never more than one point apart
        # should not be scored as though their disagreements were 1-vs-5.
        #
        # Note the symmetric all-disagreement constructions above cannot show
        # this -- there the weighting cancels between observed and expected and
        # both coefficients collapse to -1. It needs a realistic mix.
        pairs = [(1, 1)] * 5 + [(2, 2)] * 5 + [(3, 3)] * 5 + [(3, 4)] * 5
        unweighted = cohen_kappa(pairs, FIVE)
        weighted = cohen_kappa(pairs, FIVE, weighted=True)
        assert unweighted == pytest.approx(2 / 3, abs=1e-6)
        assert weighted == pytest.approx(0.875, abs=1e-6)
        assert weighted > unweighted

    def test_empty_input(self):
        assert cohen_kappa([], FIVE) is None


class TestICC:
    # Shrout & Fleiss (1979), the standard worked example. ICC(2,k) = .620
    SF = [[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8],
          [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]]

    def test_matches_shrout_fleiss_reference(self):
        assert icc_2k(self.SF) == pytest.approx(0.620, abs=0.005)

    def test_identical_raters_give_one(self):
        assert icc_2k([[5, 5], [7, 7], [9, 9], [2, 2]]) == pytest.approx(1.0)

    def test_absolute_agreement_not_consistency(self):
        # Rater B is always exactly 20 points above rater A. The ranking is
        # identical, so a consistency ICC would return 1.0. We need absolute
        # agreement: two experts who disagree by 20 points on every participant
        # do not agree about how skilled anyone is.
        shifted = [[10, 30], [20, 40], [30, 50], [40, 60], [50, 70]]
        assert icc_2k(shifted) < 0.90

    @pytest.mark.parametrize("bad", [
        [[1, 2]],           # one target
        [[1], [2], [3]],    # one rater
        [[1, 2], [3]],      # ragged
        [],                 # empty
    ])
    def test_degenerate_shapes_return_none(self, bad):
        assert icc_2k(bad) is None
