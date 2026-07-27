"""
rater_agreement.py — Inter-rater agreement for the two expert instruments.

WHY IT IS RUN DURING ONBOARDING, NOT ONLY AT ANALYSIS
The rubric's onboarding procedure has raters score practice reports, discuss
disagreements, then score a third. That procedure only works if the disagreement
is actually measured: "we broadly agreed" is not a criterion, and by the time the
real ratings are in it is too late to revise the anchors. Run this after the
practice round, and again on the real data.

WHAT IT COMPUTES
  feedback_rating (RQ4, ordinal 1-5, four dimensions)
    - percent agreement, exact and within-one
    - Cohen's kappa, unweighted and quadratic-weighted
      Unweighted kappa treats 4-vs-5 as badly as 1-vs-5, which is wrong for an
      ordered scale; quadratic weighting is the standard choice and is the one
      to report. Both are shown because a large gap between them means the
      disagreements are near-misses rather than genuine conflicts, and that
      distinction changes what you do about it.

  expert_rating (H2, continuous 0-100, seven dimensions)
    - ICC(2,k): two-way random effects, absolute agreement, average measures.
      This is the coefficient the pre-registration names. Absolute agreement,
      not consistency: two raters who rank participants identically but differ
      by 20 points throughout do not agree for our purposes.

No third-party numerical libraries: the arithmetic is a few sums, and pinning
scipy for it would make the tool harder to run on the study machine than the
analysis it supports.

Usage:
    python tools/research/rater_agreement.py                  # both instruments
    python tools/research/rater_agreement.py --instrument feedback
    python tools/research/rater_agreement.py --round 1
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
from collections import defaultdict

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

FEEDBACK_DIMS = ["relevance", "specificity", "actionability", "accuracy"]

# Conventional bands. Reported alongside the number so a reader does not have to
# supply them from memory; they are conventions, not thresholds with any
# inferential force.
def kappa_band(k):
    if k < 0.00: return "worse than chance"
    if k < 0.21: return "slight"
    if k < 0.41: return "fair"
    if k < 0.61: return "moderate"
    if k < 0.81: return "substantial"
    return "almost perfect"


def icc_band(v):
    if v < 0.50: return "poor"
    if v < 0.75: return "moderate"
    if v < 0.90: return "good"
    return "excellent"


def connect():
    import psycopg2
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST, port=ANALYTICS_DB_PORT, dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER, password=ANALYTICS_DB_PASSWORD,
    )


def cohen_kappa(pairs, categories, weighted=False):
    """pairs: [(rating_a, rating_b)]. Returns kappa or None if undefined."""
    n = len(pairs)
    if n == 0:
        return None

    idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    obs = [[0] * k for _ in range(k)]
    for a, b in pairs:
        obs[idx[a]][idx[b]] += 1

    row = [sum(obs[i]) / n for i in range(k)]
    col = [sum(obs[i][j] for i in range(k)) / n for j in range(k)]

    if weighted:
        # Quadratic weights, normalised so identical = 0 penalty, extremes = 1.
        span = (k - 1) ** 2
        w = [[((i - j) ** 2) / span for j in range(k)] for i in range(k)]
        po = sum(w[i][j] * obs[i][j] / n for i in range(k) for j in range(k))
        pe = sum(w[i][j] * row[i] * col[j] for i in range(k) for j in range(k))
        # For weighted kappa the weights are disagreement, so the formula flips.
        if pe == 0:
            return None
        return 1 - po / pe

    po = sum(obs[i][i] for i in range(k)) / n
    pe = sum(row[i] * col[i] for i in range(k))
    if pe == 1:
        # Both raters used a single identical category throughout: kappa is
        # undefined, and reporting 0 or 1 here would both be misleading.
        return None
    return (po - pe) / (1 - pe)


def icc_2k(matrix):
    """ICC(2,k), two-way random, absolute agreement, average measures.

    matrix: rows = targets, cols = raters. Every cell must be present.
    """
    n = len(matrix)
    if n < 2:
        return None
    k = len(matrix[0])
    if k < 2 or any(len(r) != k for r in matrix):
        return None

    grand = sum(sum(r) for r in matrix) / (n * k)
    row_m = [sum(r) / k for r in matrix]
    col_m = [sum(matrix[i][j] for i in range(n)) / n for j in range(k)]

    ss_rows = k * sum((rm - grand) ** 2 for rm in row_m)
    ss_cols = n * sum((cm - grand) ** 2 for cm in col_m)
    ss_tot = sum((matrix[i][j] - grand) ** 2 for i in range(n) for j in range(k))
    ss_err = ss_tot - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (k - 1)
    ms_err = ss_err / ((n - 1) * (k - 1))

    denom = ms_rows + (ms_cols - ms_err) / n
    if denom == 0:
        return None
    return (ms_rows - ms_err) / denom


def report_feedback(conn, round_no):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT participant_code, round_no, rater_id,
                   {', '.join(FEEDBACK_DIMS)}
            FROM feedback_rating
            {'WHERE round_no = %s' if round_no else ''}
            """,
            (round_no,) if round_no else (),
        )
        rows = cur.fetchall()

    if not rows:
        print("  no feedback_rating rows for this selection.")
        return

    by_unit = defaultdict(dict)
    raters = set()
    for code, rnd, rater, *scores in rows:
        by_unit[(code, rnd)][rater] = scores
        raters.add(rater)

    print(f"  {len(rows)} rating(s) · {len(by_unit)} report(s) · "
          f"{len(raters)} rater(s): {', '.join(sorted(raters))}")

    doubled = {u: r for u, r in by_unit.items() if len(r) >= 2}
    singles = len(by_unit) - len(doubled)
    if singles:
        # Named explicitly: the rubric requires two raters per report for kappa,
        # and a quiet average over whatever happens to be there would hide that
        # the requirement was not met.
        print(f"  WARNING: {singles} report(s) rated by only one rater — "
              f"excluded from agreement, and they do not satisfy the "
              f"two-rater requirement.")
    if not doubled:
        print("  no report has two or more raters; agreement is not computable.")
        return

    print()
    for di, dim in enumerate(FEEDBACK_DIMS):
        pairs = []
        for unit, ratings in doubled.items():
            for ra, rb in itertools.combinations(sorted(ratings), 2):
                a, b = ratings[ra][di], ratings[rb][di]
                if a is not None and b is not None:
                    pairs.append((a, b))
        if not pairs:
            print(f"  {dim:14s} no complete pairs")
            continue

        exact = sum(1 for a, b in pairs if a == b) / len(pairs)
        within1 = sum(1 for a, b in pairs if abs(a - b) <= 1) / len(pairs)
        ku = cohen_kappa(pairs, [1, 2, 3, 4, 5], weighted=False)
        kw = cohen_kappa(pairs, [1, 2, 3, 4, 5], weighted=True)

        def fmt(v):
            return f"{v:+.3f} ({kappa_band(v)})" if v is not None else "undefined"

        print(f"  {dim:14s} n={len(pairs):<4d} exact={exact:.0%} "
              f"within1={within1:.0%}")
        print(f"                 kappa unweighted {fmt(ku)}")
        print(f"                 kappa quadratic  {fmt(kw)}   <- report this one")


def report_expert(conn, round_no):
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT participant_code, round_no, dimension, rater_id, score
            FROM expert_rating
            {'WHERE round_no = %s' if round_no else ''}
            """,
            (round_no,) if round_no else (),
        )
        rows = cur.fetchall()

    if not rows:
        print("  no expert_rating rows for this selection.")
        return

    by_dim = defaultdict(lambda: defaultdict(dict))
    raters = set()
    for code, rnd, dim, rater, score in rows:
        by_dim[dim][(code, rnd)][rater] = float(score)
        raters.add(rater)

    print(f"  {len(rows)} rating(s) · {len(by_dim)} dimension(s) · "
          f"{len(raters)} rater(s): {', '.join(sorted(raters))}")
    print()

    common = sorted(raters)
    for dim in sorted(by_dim):
        units = by_dim[dim]
        complete = [[u[r] for r in common] for u in units.values()
                    if all(r in u for r in common)]
        dropped = len(units) - len(complete)
        v = icc_2k(complete)
        note = f"  ({dropped} incomplete dropped)" if dropped else ""
        if v is None:
            print(f"  {dim:18s} ICC not computable "
                  f"(targets={len(complete)}, raters={len(common)}){note}")
        else:
            print(f"  {dim:18s} ICC(2,k) = {v:.3f} ({icc_band(v)})  "
                  f"targets={len(complete)}{note}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instrument", choices=["feedback", "expert", "both"],
                    default="both")
    ap.add_argument("--round", type=int, default=None)
    args = ap.parse_args()

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("error: psycopg2 is required. Run this on the server.", file=sys.stderr)
        return 2

    conn = connect()
    try:
        if args.instrument in ("feedback", "both"):
            print("Feedback quality rubric (RQ4) — Cohen's kappa")
            print("-" * 66)
            report_feedback(conn, args.round)
            print()
        if args.instrument in ("expert", "both"):
            print("Expert skill rubric (H2) — ICC(2,k)")
            print("-" * 66)
            report_expert(conn, args.round)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
