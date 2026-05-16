"""
Inferential statistics pipeline for the CTF skill-feedback study.

Runs the full set of hypothesis tests required by the manuscript and
exports results as both JSON and LaTeX tables (paper-ready).

Hypotheses tested:
  H1: treatment shows greater skill gain than control
      -> Mann-Whitney U (between), Wilcoxon signed-rank (within)
  H2: 7-dim instrument reliable (delegated to validation_service)
  H3: treatment reports higher satisfaction/self-efficacy
      -> Mann-Whitney U on survey scores

Usage:
    python tools/analysis/statistical_tests.py --out-dir analysis/results/

Environment variables:
    ANALYTICS_DB_HOST, ANALYTICS_DB_PORT, ANALYTICS_DB_NAME,
    ANALYTICS_DB_USER, ANALYTICS_DB_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

DIMENSIONS = [
    "accuracy_score", "persistence_score", "web_recon_score",
    "protocol_score", "ssh_pivot_score", "blue_analysis_score",
    "time_efficiency_score",
]

DIMENSION_LABELS = {
    "accuracy_score": "Accuracy",
    "persistence_score": "Persistence",
    "web_recon_score": "Web Recon",
    "protocol_score": "Protocol",
    "ssh_pivot_score": "SSH Pivot",
    "blue_analysis_score": "Blue Analysis",
    "time_efficiency_score": "Time Efficiency",
}

ALPHA = 0.05


def _get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST, port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME, user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def _fetch_scores(condition: str | None = None, round_no: int | None = None) -> list[dict]:
    """Fetch skill scores, optionally filtered by condition and/or round."""
    sql = """
        SELECT r.user_key, r.accuracy_score, r.persistence_score,
               r.web_recon_score, r.protocol_score, r.ssh_pivot_score,
               r.blue_analysis_score, r.time_efficiency_score,
               e.condition, e.round_no
        FROM user_skill_reports r
        LEFT JOIN experiment_assignment e ON r.user_key = CAST(e.user_id AS TEXT)
    """
    clauses, params = [], []
    if condition:
        clauses.append("e.condition = %s")
        params.append(condition)
    if round_no is not None:
        clauses.append("e.round_no = %s")
        params.append(round_no)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Core statistical functions
# ---------------------------------------------------------------------------

def wilcoxon_within(group: str, dimension: str) -> dict[str, Any]:
    """
    Wilcoxon signed-rank test comparing pre (round 1) vs post (round 3)
    scores within one condition group.

    Returns:
        statistic, p_value, n, effect_size_r, median_pre,
        median_post, significant
    """
    try:
        import numpy as np
        from scipy import stats as sp
    except ImportError:
        return {"skipped": True, "reason": "scipy not installed"}

    pre = _fetch_scores(condition=group, round_no=1)
    post = _fetch_scores(condition=group, round_no=3)

    pre_map = {r["user_key"]: r[dimension] for r in pre if r.get(dimension) is not None}
    post_map = {r["user_key"]: r[dimension] for r in post if r.get(dimension) is not None}
    common = sorted(set(pre_map) & set(post_map))

    if len(common) < 3:
        return {"skipped": True, "reason": f"insufficient paired data (n={len(common)})"}

    x_pre = np.array([pre_map[k] for k in common])
    x_post = np.array([post_map[k] for k in common])

    stat, p = sp.wilcoxon(x_post, x_pre, alternative="greater")
    n = len(common)
    # Effect size r = Z / sqrt(N)
    z = sp.norm.ppf(1 - p / 2)
    effect_r = abs(z) / (n ** 0.5)

    return {
        "statistic": round(float(stat), 4),
        "p_value": round(float(p), 4),
        "n": n,
        "effect_size_r": round(float(effect_r), 4),
        "median_pre": round(float(np.median(x_pre)), 2),
        "median_post": round(float(np.median(x_post)), 2),
        "significant": bool(p < ALPHA),
    }


def mann_whitney_between(dimension: str, timepoint: str = "post") -> dict[str, Any]:
    """
    Mann-Whitney U test comparing control vs treatment at a given timepoint.

    Returns:
        U, p_value, effect_size_r (rank-biserial), median_control,
        median_treatment, significant
    """
    try:
        import numpy as np
        from scipy import stats as sp
    except ImportError:
        return {"skipped": True, "reason": "scipy not installed"}

    round_no = 3 if timepoint == "post" else 1
    ctrl = _fetch_scores(condition="control", round_no=round_no)
    trt = _fetch_scores(condition="treatment", round_no=round_no)

    x_ctrl = np.array([r[dimension] for r in ctrl if r.get(dimension) is not None], dtype=float)
    x_trt = np.array([r[dimension] for r in trt if r.get(dimension) is not None], dtype=float)

    if len(x_ctrl) < 2 or len(x_trt) < 2:
        return {"skipped": True, "reason": "insufficient data"}

    stat, p = sp.mannwhitneyu(x_trt, x_ctrl, alternative="greater")
    # Rank-biserial effect size
    r_rb = 1 - (2 * stat) / (len(x_ctrl) * len(x_trt))

    return {
        "U": round(float(stat), 2),
        "p_value": round(float(p), 4),
        "effect_size_r": round(float(r_rb), 4),
        "median_control": round(float(np.median(x_ctrl)), 2),
        "median_treatment": round(float(np.median(x_trt)), 2),
        "significant": bool(p < ALPHA),
    }


def cohens_d(dimension: str, timepoint: str = "post") -> dict[str, Any]:
    """
    Cohen's d (between-group) with pooled standard deviation.

    Returns:
        d, interpretation ('negligible', 'small', 'medium', 'large')
    """
    try:
        import numpy as np
    except ImportError:
        return {"skipped": True, "reason": "numpy not installed"}

    round_no = 3 if timepoint == "post" else 1
    ctrl = _fetch_scores(condition="control", round_no=round_no)
    trt = _fetch_scores(condition="treatment", round_no=round_no)

    x_ctrl = np.array([r[dimension] for r in ctrl if r.get(dimension) is not None], dtype=float)
    x_trt = np.array([r[dimension] for r in trt if r.get(dimension) is not None], dtype=float)

    if len(x_ctrl) < 2 or len(x_trt) < 2:
        return {"skipped": True, "reason": "insufficient data"}

    pooled_sd = (
        ((len(x_ctrl) - 1) * x_ctrl.var(ddof=1) + (len(x_trt) - 1) * x_trt.var(ddof=1))
        / (len(x_ctrl) + len(x_trt) - 2)
    ) ** 0.5

    if pooled_sd == 0:
        return {"skipped": True, "reason": "zero variance"}

    d = (x_trt.mean() - x_ctrl.mean()) / pooled_sd
    d = float(d)

    if abs(d) < 0.2:
        interp = "negligible"
    elif abs(d) < 0.5:
        interp = "small"
    elif abs(d) < 0.8:
        interp = "medium"
    else:
        interp = "large"

    return {"d": round(d, 4), "interpretation": interp}


def mixed_effects_model(dimension: str) -> dict[str, Any]:
    """
    Linear mixed model: score ~ round * condition + (1|participant).
    Gracefully skips if statsmodels is not installed.
    """
    try:
        import numpy as np
        import pandas as pd
        import statsmodels.formula.api as smf
    except ImportError as exc:
        return {"skipped": True, "reason": f"statsmodels not installed: {exc}"}

    all_scores = _fetch_scores()
    if len(all_scores) < 10:
        return {"skipped": True, "reason": "insufficient data (need >= 10)"}

    df = pd.DataFrame(all_scores)
    df = df.dropna(subset=[dimension, "condition", "round_no"])
    df["condition_num"] = (df["condition"] == "treatment").astype(int)

    try:
        model = smf.mixedlm(
            f"{dimension} ~ round_no * condition_num",
            df, groups=df["user_key"],
        ).fit(reml=True)

        fe = model.fe_params.to_dict()
        pvalues = model.pvalues.to_dict()
        interaction_p = pvalues.get("round_no:condition_num", None)

        return {
            "fixed_effects": {k: round(float(v), 4) for k, v in fe.items()},
            "interaction_p": round(float(interaction_p), 4) if interaction_p is not None else None,
            "aic": round(float(model.aic), 2),
            "bic": round(float(model.bic), 2),
        }
    except Exception as exc:
        return {"skipped": True, "reason": str(exc)}


def holm_bonferroni(p_values: dict[str, float]) -> dict[str, float]:
    """
    Holm-Bonferroni multiple-comparison correction.

    Args:
        p_values: {dimension: raw_p}

    Returns:
        {dimension: adjusted_p} for dimensions that survive alpha=0.05
    """
    import numpy as np

    keys = list(p_values.keys())
    raw = np.array([p_values[k] for k in keys])
    m = len(raw)
    order = np.argsort(raw)

    adjusted = np.zeros(m)
    for i, idx in enumerate(order):
        adjusted[idx] = min(1.0, raw[idx] * (m - i))

    # Enforce monotonicity
    for i in range(1, m):
        adjusted[order[i]] = max(adjusted[order[i]], adjusted[order[i - 1]])

    return {keys[i]: round(float(adjusted[i]), 4) for i in range(m)}


def run_all() -> dict[str, Any]:
    """
    Execute the full statistical battery for all 7 dimensions + overall.
    Apply Holm-Bonferroni correction and return structured results.
    """
    results: dict[str, Any] = {}
    mw_p_values: dict[str, float] = {}

    for dim in DIMENSIONS:
        label = DIMENSION_LABELS[dim]
        wil = wilcoxon_within("treatment", dim)
        mw = mann_whitney_between(dim, "post")
        cd = cohens_d(dim, "post")
        lmm = mixed_effects_model(dim)

        results[dim] = {
            "label": label,
            "wilcoxon_treatment": wil,
            "mann_whitney": mw,
            "cohens_d": cd,
            "mixed_model": lmm,
        }
        if isinstance(mw.get("p_value"), float):
            mw_p_values[dim] = mw["p_value"]

    if mw_p_values:
        adjusted = holm_bonferroni(mw_p_values)
        for dim, p_adj in adjusted.items():
            results[dim]["mann_whitney"]["p_adjusted"] = p_adj
            results[dim]["mann_whitney"]["significant_adjusted"] = bool(p_adj < ALPHA)

    return results


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_json(results: dict[str, Any], out_path: str) -> None:
    """Write full results as JSON."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[JSON] Written to {out_path}")


def export_latex(results: dict[str, Any], out_path: str) -> None:
    """
    Write a booktabs LaTeX table ready to paste into the manuscript.
    Columns: Dimension | Median(ctrl) | Median(trt) | U | p_adj | Cohen's d
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Between-group comparison (control vs.\ treatment) at post-test}",
        r"\label{tab:between_group}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Dimension & Med$_{ctrl}$ & Med$_{trt}$ & $U$ & $p_{adj}$ & Cohen's $d$ \\",
        r"\midrule",
    ]

    for dim in DIMENSIONS:
        r = results.get(dim, {})
        label = DIMENSION_LABELS.get(dim, dim)
        mw = r.get("mann_whitney", {})
        cd = r.get("cohens_d", {})

        med_c = mw.get("median_control", "--")
        med_t = mw.get("median_treatment", "--")
        u_val = mw.get("U", "--")
        p_adj = mw.get("p_adjusted", mw.get("p_value", "--"))
        d_val = cd.get("d", "--")
        sig = "*" if mw.get("significant_adjusted", False) else ""

        def fmt(v):
            return f"{v:.2f}" if isinstance(v, float) else str(v)

        lines.append(
            f"{label} & {fmt(med_c)} & {fmt(med_t)} & {fmt(u_val)} & {fmt(p_adj)}{sig} & {fmt(d_val)} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\multicolumn{6}{l}{\footnotesize{* Significant after Holm--Bonferroni correction ($\alpha=0.05$)}} \\",
        r"\end{tabular}",
        r"\end{table}",
    ]

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[LaTeX] Written to {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run full statistical analysis pipeline")
    parser.add_argument("--out-dir", default="analysis/results/", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Running statistical tests...")
    results = run_all()

    json_path = str(out_dir / "stats.json")
    tex_path = str(out_dir / "stats_table.tex")
    export_json(results, json_path)
    export_latex(results, tex_path)
    print("Done.")


if __name__ == "__main__":
    main()
