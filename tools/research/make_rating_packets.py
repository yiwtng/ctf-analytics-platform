"""
make_rating_packets.py — Build blinded expert-rating packets and the key file.

WHAT RQ4 NEEDS AND WHY THIS TOOL EXISTS
For each participant-round the platform generates two reports from identical
skill data: one model-generated, one from the deterministic rule-based
generator. Experts rate both. The comparison only means anything if the rater
cannot tell which is which -- otherwise they are rating their expectation of a
language model, not the text in front of them.

Blinding by intention does not survive contact with real data. The generator
name sits in `model_name`, the primary report is the one the learner saw, and
if the model-generated report were always presented first, order effects and
rater fatigue would be confounded with source. This tool removes all three:
it strips every source marker, labels the two reports A and B with the
assignment decided by a coin flip per participant-round, and writes the mapping
to a separate key file.

THE KEY FILE NEVER GOES TO THE RATERS
`--key-out` is written outside the packet directory by default and must stay
with the study coordinator. `feedback_rating.feedback_source` is filled in from
it after ratings are submitted. A rater who fills that column in has, by
definition, not been blind, and the pre-registration excludes those ratings.

Usage:
    # dry run: see what would be produced
    python tools/research/make_rating_packets.py --out packets/

    # write packets and key
    python tools/research/make_rating_packets.py --out packets/ \\
        --key-out /secure/blinding_key.csv --commit
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import sys
from pathlib import Path

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

# Deterministic per (participant, round): the same study re-run produces the same
# assignment, so a lost packet can be regenerated and still match the key.
# Randomness comes from the salt, which the coordinator sets once and keeps.
DEFAULT_SALT = os.getenv("BLINDING_SALT", "")


def connect():
    import psycopg2
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST, port=ANALYTICS_DB_PORT, dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER, password=ANALYTICS_DB_PASSWORD,
    )


def coin(salt: str, code: str, round_no: int) -> bool:
    """True means the primary report is presented as A."""
    h = hashlib.sha256(f"{salt}|{code}|{round_no}".encode()).digest()
    return h[0] & 1 == 0


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    return list(value) if isinstance(value, (list, tuple)) else [str(value)]


def render(report: dict, label: str) -> str:
    """Render one report with every source marker removed.

    Only the fields a rater is meant to judge are emitted. model_name, model,
    report_role, raw_response and generated_at are deliberately not rendered:
    each of them identifies the generator, and one is enough to unblind.
    """
    def block(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{html.escape(str(x))}</li>" for x in items)
        return f"<h3>{title}</h3><ul>{lis}</ul>"

    summary = html.escape(report.get("summary") or "")
    return f"""<div class="report">
<h2>Report {label}</h2>
{f'<p class="summary">{summary}</p>' if summary else ''}
{block("Strengths", _as_list(report.get("strengths")))}
{block("Areas to improve", _as_list(report.get("weaknesses")))}
{block("Recommendations", _as_list(report.get("recommendations")))}
</div>"""


CSS = """
body{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
     font-size:11pt;line-height:1.5;max-width:960px;margin:24px auto;padding:0 16px}
h1{font-size:15pt;border-bottom:2px solid #000;padding-bottom:6px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:16px}
.report{border:1px solid #999;padding:14px;border-radius:4px}
.report h2{font-size:12pt;margin:0 0 8px;background:#f0f0f0;padding:5px 8px;
           border-radius:3px}
.report h3{font-size:10pt;margin:12px 0 4px;color:#333}
.summary{font-style:italic;color:#222}
ul{margin:4px 0 0 18px;padding:0}li{margin-bottom:3px}
.sheet{margin-top:22px;border:1.5px solid #000;padding:12px}
table{width:100%;border-collapse:collapse;margin-top:6px;font-size:10pt}
th,td{border:1px solid #666;padding:5px 7px;text-align:left}
th{background:#eee}
.note{font-size:9.5pt;color:#444;margin-top:8px}
@media print{.pair{grid-template-columns:1fr 1fr}body{margin:0}}
"""

DIMS = ["Relevance", "Specificity", "Actionability", "Accuracy"]


def packet_html(code: str, round_no: int, rep_a: dict, rep_b: dict) -> str:
    rows = "".join(
        f"<tr><td>{d}</td><td></td><td></td></tr>" for d in DIMS
    )
    return f"""<!doctype html><meta charset="utf-8">
<title>Rating packet {code} R{round_no}</title><style>{CSS}</style>
<h1>Feedback rating — participant {code}, round {round_no}</h1>
<p>Two reports were produced for this participant from the same underlying data.
Rate each one on all four dimensions using the rubric. Judge only the text in
front of you.</p>
<div class="pair">{render(rep_a, "A")}{render(rep_b, "B")}</div>
<div class="sheet">
<strong>Ratings</strong> (1&ndash;5 each; see rubric for anchors)
<table><tr><th>Dimension</th><th>Report A</th><th>Report B</th></tr>{rows}</table>
<p class="note">A comment is required for any rating of 1 or 2.<br>
Comment A: ______________________________________________<br>
Comment B: ______________________________________________</p>
<p class="note"><strong>Do not record which generator produced which report.</strong>
That column is completed by the study coordinator after your ratings are
submitted. If you believe you can identify the source, say so in the comment —
it is useful evidence about the blinding, and it does not invalidate your
rating.</p>
</div>
<p class="note">Rater ID: ________ &nbsp;&nbsp; Date: ________</p>"""


def fetch_pairs(conn, code_map):
    """Return [(code, round_no, primary, shadow)] for rounds having both."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_key, round_no, report_role, summary, strengths,
                   weaknesses, recommendations
            FROM user_ai_reports
            WHERE report_role IN ('primary','shadow') AND round_no IS NOT NULL
            ORDER BY user_key, round_no, report_role
            """
        )
        rows = cur.fetchall()

    bucket: dict[tuple, dict] = {}
    for user_key, round_no, role, summary, strengths, weak, recs in rows:
        code = code_map.get(str(user_key))
        if code is None:
            continue
        bucket.setdefault((code, round_no), {})[role] = {
            "summary": summary, "strengths": strengths,
            "weaknesses": weak, "recommendations": recs,
        }

    out, skipped = [], []
    for (code, round_no), r in sorted(bucket.items()):
        if "primary" in r and "shadow" in r:
            out.append((code, round_no, r["primary"], r["shadow"]))
        else:
            skipped.append((code, round_no, sorted(r)))
    return out, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="packets/", help="directory for rater packets")
    ap.add_argument("--key-out", default=None,
                    help="path for the blinding key (default: alongside --out, "
                         "NOT inside it)")
    ap.add_argument("--salt", default=DEFAULT_SALT,
                    help="blinding salt; set once and keep with the key")
    ap.add_argument("--commit", action="store_true",
                    help="write files (default lists what would be written)")
    args = ap.parse_args()

    if args.commit and not args.salt:
        print("error: --salt (or BLINDING_SALT) is required to write packets.\n"
              "Without it the A/B assignment is predictable from the participant "
              "code alone, which is not blinding.", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    key_path = Path(args.key_out) if args.key_out else out_dir.parent / "blinding_key.csv"

    if args.commit and key_path.resolve().is_relative_to(out_dir.resolve()):
        print(f"error: the key file ({key_path}) is inside the packet directory "
              f"({out_dir}). Raters receive that directory.", file=sys.stderr)
        return 2

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("error: psycopg2 is required. Run this on the server.", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).parent))
    from export_anonymized_dataset import build_code_map, ExportError

    try:
        code_map = build_code_map()
    except ExportError as exc:
        print(f"cannot build packets: {exc}", file=sys.stderr)
        return 1

    conn = connect()
    try:
        pairs, skipped = fetch_pairs(conn, code_map)
    finally:
        conn.close()

    if skipped:
        # Loudly, not silently: a missing shadow report means RQ4 loses that
        # participant-round, and a quiet packet count would hide it.
        print(f"WARNING: {len(skipped)} participant-round(s) have only one report "
              f"and are excluded from RQ4:", file=sys.stderr)
        for code, rnd, roles in skipped[:10]:
            print(f"  {code} round {rnd}: only {', '.join(roles)}", file=sys.stderr)
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more", file=sys.stderr)

    if not pairs:
        print("No participant-round has both a primary and a shadow report. "
              "Nothing to rate.")
        return 1

    print(f"{len(pairs)} packet(s) to produce, from {len({p[0] for p in pairs})} "
          f"participant(s).")

    if not args.commit:
        print("\nDry run. Re-run with --commit and --salt to write.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    key_rows = []
    for code, round_no, primary, shadow in pairs:
        primary_is_a = coin(args.salt, code, round_no)
        rep_a, rep_b = (primary, shadow) if primary_is_a else (shadow, primary)
        name = f"{code}_R{round_no}.html"
        (out_dir / name).write_text(packet_html(code, round_no, rep_a, rep_b),
                                    encoding="utf-8")
        key_rows.append({
            "packet": name, "participant_code": code, "round_no": round_no,
            "report_A": "primary" if primary_is_a else "shadow",
            "report_B": "shadow" if primary_is_a else "primary",
        })

    with open(key_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(key_rows[0]))
        w.writeheader()
        w.writerows(key_rows)

    n_a = sum(1 for r in key_rows if r["report_A"] == "primary")
    print(f"\nWrote {len(key_rows)} packet(s) to {out_dir}/")
    print(f"Wrote the key to {key_path}")
    print(f"  primary presented as A in {n_a} of {len(key_rows)} packets "
          f"({n_a / len(key_rows):.0%})")
    print("\nGive raters the packet directory only. The key stays with the "
          "coordinator until every rating is submitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
