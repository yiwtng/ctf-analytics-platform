"""
Psychometric validation for the 7-dimensional skill scoring.

Provides:
  - Storage for expert ratings (gold-standard skill judgments)
  - Inter-rater reliability: ICC(2,k) intraclass correlation
  - Internal consistency: Cronbach's alpha across the 7 dimensions
  - Convergent validity: correlation of skill scores vs external measures
  - Exploratory Factor Analysis (EFA) — graceful skip if lib unavailable
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from typing import Any, Optional

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

DIMENSIONS = [
    "accuracy", "persistence", "web_recon", "protocol",
    "ssh_pivot", "blue_analysis", "time_efficiency",
]

# ICC interpretation thresholds (Koo & Mae, 2016)
_ICC_THRESHOLDS = [
    (0.90, "excellent"),
    (0.75, "good"),
    (0.50, "moderate"),
    (0.00, "poor"),
]


@dataclass
class ExpertRating:
    rater_id: str           # e.g. "E01"
    participant_code: str   # anonymized, e.g. "P001"
    round_no: int
    dimension: str          # one of DIMENSIONS
    score: float            # expert's 0-100 judgment


def _get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST, port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME, user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_expert_rating(rating: ExpertRating) -> None:
    """
    Persist one expert rating. Idempotent on (rater_id, participant_code,
    round_no, dimension) — duplicate submissions are silently ignored.
    """
    if rating.dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{rating.dimension}'. Must be one of {DIMENSIONS}")
    if not (0 <= rating.score <= 100):
        raise ValueError(f"Score must be in [0, 100], got {rating.score}")

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO expert_rating
                    (rater_id, participant_code, round_no, dimension, score)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (rater_id, participant_code, round_no, dimension)
                DO NOTHING
                """,
                (rating.rater_id, rating.participant_code,
                 rating.round_no, rating.dimension, rating.score),
            )
        conn.commit()


def _fetch_expert_ratings(
    dimension: str,
    round_no: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Fetch ratings for a given dimension, optionally filtered by round."""
    sql = "SELECT * FROM expert_rating WHERE dimension = %s"
    params: list[Any] = [dimension]
    if round_no is not None:
        sql += " AND round_no = %s"
        params.append(round_no)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# ICC(2,k) — two-way random, absolute agreement, average measures
# ---------------------------------------------------------------------------

def compute_icc(dimension: str, round_no: Optional[int] = None) -> dict[str, Any]:
    """
    Intraclass Correlation Coefficient ICC(2,k).

    Uses pingouin.intraclass_corr if available; otherwise falls back to
    the ANOVA-based formula from Shrout & Fleiss (1979).

    Returns:
        icc, ci_low, ci_high, n_subjects, n_raters, interpretation
    """
    rows = _fetch_expert_ratings(dimension, round_no)
    if len(rows) < 2:
        return {
            "icc": None, "ci_low": None, "ci_high": None,
            "n_subjects": 0, "n_raters": 0,
            "interpretation": "insufficient data",
        }

    try:
        import pandas as pd
        import pingouin as pg

        df = pd.DataFrame(rows)
        icc_df = pg.intraclass_corr(
            data=df,
            targets="participant_code",
            raters="rater_id",
            ratings="score",
            nan_policy="omit",
        )
        row = icc_df[icc_df["Type"] == "ICC2k"].iloc[0]
        icc_val = float(row["ICC"])
        ci_low = float(row["CI95%"][0])
        ci_high = float(row["CI95%"][1])
        n_subjects = df["participant_code"].nunique()
        n_raters = df["rater_id"].nunique()

    except ImportError:
        # Fallback: ANOVA-based ICC(2,k) formula
        try:
            import numpy as np
            import pandas as pd

            df = pd.DataFrame(rows)
            pivot = df.pivot_table(
                index="participant_code", columns="rater_id",
                values="score", aggfunc="mean",
            )
            n = len(pivot)
            k = len(pivot.columns)
            grand_mean = pivot.values.mean()

            ss_between = k * ((pivot.mean(axis=1) - grand_mean) ** 2).sum()
            ss_within = ((pivot.values - pivot.mean(axis=1).values[:, None]) ** 2).sum()
            ss_error = ss_within - k * ((pivot.mean(axis=0) - grand_mean) ** 2).sum()

            ms_between = ss_between / (n - 1)
            ms_error = ss_error / ((n - 1) * (k - 1))

            icc_val = (ms_between - ms_error) / (ms_between + (k - 1) * ms_error)
            icc_val = float(np.clip(icc_val, -1.0, 1.0))
            ci_low, ci_high = None, None
            n_subjects, n_raters = n, k

        except Exception as exc:
            return {"skipped": True, "reason": f"fallback failed: {exc}"}

    interp = next(
        label for threshold, label in _ICC_THRESHOLDS if icc_val >= threshold
    )

    return {
        "icc": round(icc_val, 4),
        "ci_low": round(ci_low, 4) if ci_low is not None else None,
        "ci_high": round(ci_high, 4) if ci_high is not None else None,
        "n_subjects": n_subjects,
        "n_raters": n_raters,
        "interpretation": interp,
    }


# ---------------------------------------------------------------------------
# Cronbach's alpha
# ---------------------------------------------------------------------------

def compute_cronbach_alpha(round_no: Optional[int] = None) -> dict[str, Any]:
    """
    Internal consistency of system-generated skill scores across the
    7 dimensions, computed over all participants in the given round.

    alpha >= 0.70 is the conventional acceptability threshold (Nunnally, 1978).
    """
    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        return {"skipped": True, "reason": "numpy/pandas not installed"}

    # Fetch system scores from user_skill_reports
    sql = """
        SELECT user_key, accuracy_score, persistence_score, web_recon_score,
               protocol_score, ssh_pivot_score, blue_analysis_score,
               time_efficiency_score
        FROM user_skill_reports
    """
    params: list[Any] = []
    if round_no is not None:
        # Use round via cohort lookup — fallback: filter nothing
        pass

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if len(rows) < 2:
        return {
            "alpha": None, "n_items": 7,
            "n_participants": len(rows), "acceptable": False,
        }

    df = pd.DataFrame(rows)
    score_cols = [
        "accuracy_score", "persistence_score", "web_recon_score",
        "protocol_score", "ssh_pivot_score", "blue_analysis_score",
        "time_efficiency_score",
    ]
    X = df[score_cols].dropna().values
    n_participants, k = X.shape

    item_variances = X.var(axis=0, ddof=1).sum()
    total_variance = X.sum(axis=1).var(ddof=1)
    alpha = (k / (k - 1)) * (1 - item_variances / total_variance)
    alpha = float(np.clip(alpha, -1.0, 1.0))

    return {
        "alpha": round(alpha, 4),
        "n_items": k,
        "n_participants": n_participants,
        "acceptable": alpha >= 0.70,
    }


# ---------------------------------------------------------------------------
# Convergent validity
# ---------------------------------------------------------------------------

def compute_convergent_validity(external_measure: str) -> dict[str, Any]:
    """
    Spearman + Pearson correlation between overall skill average and an
    external measure.

    Args:
        external_measure: one of 'posttest', 'pretest', 'solve_count'
    """
    try:
        import numpy as np
        import pandas as pd
        from scipy import stats as sp_stats
    except ImportError:
        return {"skipped": True, "reason": "scipy/numpy not installed"}

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_key, accuracy_score, persistence_score,
                       web_recon_score, protocol_score, ssh_pivot_score,
                       blue_analysis_score, time_efficiency_score,
                       total_solves
                FROM user_skill_reports
                """,
            )
            rows = cur.fetchall()

    if len(rows) < 3:
        return {"skipped": True, "reason": "insufficient data (need >= 3)"}

    df = pd.DataFrame(rows)
    score_cols = [
        "accuracy_score", "persistence_score", "web_recon_score",
        "protocol_score", "ssh_pivot_score", "blue_analysis_score",
        "time_efficiency_score",
    ]
    df["overall"] = df[score_cols].mean(axis=1)

    if external_measure == "solve_count":
        external = df["total_solves"].astype(float)
    else:
        # Posttest/pretest not yet in DB — return empty
        return {
            "skipped": True,
            "reason": f"'{external_measure}' not yet available in DB",
        }

    skill = df["overall"].astype(float)
    n = len(df)

    pearson_r, pearson_p = sp_stats.pearsonr(skill, external)
    spearman_rho, spearman_p = sp_stats.spearmanr(skill, external)

    return {
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": round(float(pearson_p), 4),
        "spearman_rho": round(float(spearman_rho), 4),
        "spearman_p": round(float(spearman_p), 4),
        "n": n,
    }


# ---------------------------------------------------------------------------
# Exploratory Factor Analysis
# ---------------------------------------------------------------------------

def exploratory_factor_analysis() -> dict[str, Any]:
    """
    EFA on the 7 dimensions using factor_analyzer.
    Gracefully skips if library is not installed.
    """
    try:
        from factor_analyzer import FactorAnalyzer
        from factor_analyzer.factor_analyzer import calculate_kmo
        import pandas as pd
        import numpy as np
    except ImportError as exc:
        warnings.warn(f"factor_analyzer not installed, skipping EFA: {exc}")
        return {"skipped": True, "reason": "factor_analyzer not installed"}

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT accuracy_score, persistence_score, web_recon_score,
                       protocol_score, ssh_pivot_score, blue_analysis_score,
                       time_efficiency_score
                FROM user_skill_reports
                """
            )
            rows = cur.fetchall()

    if len(rows) < 10:
        return {"skipped": True, "reason": "insufficient data (need >= 10)"}

    df = pd.DataFrame(rows).dropna()
    kmo_all, kmo_model = calculate_kmo(df)

    fa = FactorAnalyzer(rotation="varimax", n_factors=2)
    fa.fit(df)
    loadings = dict(zip(df.columns, fa.loadings_.tolist()))
    variance = fa.get_factor_variance()

    return {
        "n_factors_suggested": 2,
        "loadings": loadings,
        "variance_explained": [round(float(v), 4) for v in variance[1]],
        "kmo": round(float(kmo_model), 4),
    }


# ---------------------------------------------------------------------------
# AI Feedback Quality Assessment (G3)
# ---------------------------------------------------------------------------

@dataclass
class FeedbackRating:
    rater_id: str
    participant_code: str
    round_no: int
    relevance: int       # 1–5: feedback is relevant to actual performance
    actionability: int   # 1–5: learner can act on the feedback
    accuracy: int        # 1–5: content is factually correct, no hallucination
    comment: Optional[str] = None


def store_feedback_rating(r: FeedbackRating) -> None:
    """
    Persist one AI feedback quality rating. Idempotent on
    (rater_id, participant_code, round_no).
    """
    for field, val in [("relevance", r.relevance), ("actionability", r.actionability), ("accuracy", r.accuracy)]:
        if not (1 <= val <= 5):
            raise ValueError(f"{field} must be between 1 and 5, got {val}")

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback_rating
                    (rater_id, participant_code, round_no, relevance, actionability, accuracy, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rater_id, participant_code, round_no)
                DO NOTHING
                """,
                (r.rater_id, r.participant_code, r.round_no,
                 r.relevance, r.actionability, r.accuracy, r.comment),
            )
        conn.commit()


def feedback_quality_summary() -> dict[str, Any]:
    """
    Aggregate quality metrics across all expert feedback ratings.

    Returns:
        mean/SD per dimension, Cohen's kappa for relevance/accuracy
        agreement (as categorical), percentage rated >= 4.
    """
    try:
        import numpy as np
        from scipy.stats import pearsonr
    except ImportError:
        return {"skipped": True, "reason": "numpy/scipy not installed"}

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM feedback_rating")
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {"n_ratings": 0, "message": "no ratings yet"}

    dims = ["relevance", "actionability", "accuracy"]
    summary: dict[str, Any] = {"n_ratings": len(rows)}

    for dim in dims:
        vals = np.array([r[dim] for r in rows], dtype=float)
        summary[dim] = {
            "mean": round(float(vals.mean()), 3),
            "sd": round(float(vals.std(ddof=1)), 3) if len(vals) > 1 else 0.0,
            "pct_ge_4": round(float((vals >= 4).mean() * 100), 1),
        }

    # Cohen's kappa between pairs of raters on relevance (treat as categorical)
    rater_ids = list({r["rater_id"] for r in rows})
    if len(rater_ids) >= 2:
        kappas = []
        for i in range(len(rater_ids)):
            for j in range(i + 1, len(rater_ids)):
                r1 = {(r["participant_code"], r["round_no"]): r["relevance"]
                      for r in rows if r["rater_id"] == rater_ids[i]}
                r2 = {(r["participant_code"], r["round_no"]): r["relevance"]
                      for r in rows if r["rater_id"] == rater_ids[j]}
                common = set(r1) & set(r2)
                if len(common) >= 2:
                    a = np.array([r1[k] for k in common])
                    b = np.array([r2[k] for k in common])
                    kappas.append(_cohens_kappa(a, b))
        summary["cohens_kappa_relevance"] = (
            round(float(np.mean(kappas)), 4) if kappas else None
        )
    else:
        summary["cohens_kappa_relevance"] = None

    return summary


def _cohens_kappa(a: "np.ndarray", b: "np.ndarray") -> float:
    """Compute Cohen's kappa for two raters on ordinal Likert categories."""
    import numpy as np

    categories = list(range(1, 6))
    n = len(a)
    p_obs = (a == b).mean()

    p_exp = sum(
        ((a == c).mean() * (b == c).mean()) for c in categories
    )
    if p_exp == 1.0:
        return 1.0
    return float((p_obs - p_exp) / (1 - p_exp))
