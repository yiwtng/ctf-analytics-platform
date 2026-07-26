"""
import_survey_responses.py — Load questionnaire responses into survey_response.

WHY THIS EXISTS
Migration 013 created survey_response, but nothing in the platform writes to it:
there is no questionnaire UI and no endpoint. Without an import path the
self-efficacy scale cannot be collected at all, and H3 is untestable no matter
how carefully it is pre-registered.

The scale is administered before Round 1 -- before the participant has touched
the platform -- so delivering it outside the platform (paper, or an institutional
form) is the natural choice rather than a workaround. What matters is that the
responses land in the database in a shape the analysis can use, validated on the
way in. That is this script's whole job.

INPUT: wide CSV, one row per participant, one column per item. This is what form
tools export and what a hand-entered sheet looks like.

    participant_code,cse_web_1,cse_web_2,...,cse_time_2
    P001,60,50,...,70

VALIDATION IS THE POINT
Every item code is checked against the instrument definition below. An unknown
column is an error, not a row silently inserted with a typo'd item_code -- a
renamed form field would otherwise produce data that looks fine until alpha is
computed over the wrong item set. Out-of-range and non-numeric values are
likewise errors. Nothing is written unless the whole file validates.

Re-running is safe: rows are upserted on the natural key, so a corrected file
replaces the earlier values instead of duplicating them and inflating n.

Usage:
    # validate only (default -- always do this first)
    python tools/research/import_survey_responses.py --file pre.csv --occasion pre

    # write
    python tools/research/import_survey_responses.py --file pre.csv --occasion pre --commit
"""

import argparse
import csv
import os
import sys
from decimal import Decimal, InvalidOperation

# psycopg2 is imported inside connect(), not here. Validation touches no
# database, and it is meant to be run on a spreadsheet from the researcher's own
# machine before the file goes anywhere near the server -- requiring a Postgres
# driver for that would defeat the purpose.

ANALYTICS_DB_HOST = os.getenv("ANALYTICS_DB_HOST", "analytics_db")
ANALYTICS_DB_PORT = int(os.getenv("ANALYTICS_DB_PORT", "5432"))
ANALYTICS_DB_NAME = os.getenv("ANALYTICS_DB_NAME", "analytics")
ANALYTICS_DB_USER = os.getenv("ANALYTICS_DB_USER", "analytics")
ANALYTICS_DB_PASSWORD = os.getenv("ANALYTICS_DB_PASSWORD", "analytics")

# Instrument definitions. Item codes here are the authority: the CSV is checked
# against them, not the other way round. Adding or rewording an item means a new
# version string, so that responses to different wordings stay distinguishable
# in the same table.
INSTRUMENTS = {
    "cse": {
        "version": "v1",
        "scale_min": Decimal("0"),
        "scale_max": Decimal("100"),
        "items": [
            "cse_web_1", "cse_web_2",
            "cse_proto_1", "cse_proto_2",
            "cse_ssh_1", "cse_ssh_2",
            "cse_blue_1", "cse_blue_2",
            "cse_acc_1", "cse_acc_2",
            "cse_pers_1", "cse_pers_2",
            "cse_time_1", "cse_time_2",
        ],
        # More than this many blanks and the participant's total is not
        # computable; the pre-registration treats the case as missing on H3.
        "max_blank": 2,
        # Both are required for this instrument. This is not merely tidiness:
        # Postgres treats NULLs as distinct in a unique constraint, so a row with
        # a NULL round_no or occasion can never conflict with itself and the
        # upsert below would insert a duplicate on every re-run.
        "requires": ("round", "occasion"),
    },
}

ID_COLUMN = "participant_code"


def connect():
    import psycopg2
    return psycopg2.connect(
        host=ANALYTICS_DB_HOST,
        port=ANALYTICS_DB_PORT,
        dbname=ANALYTICS_DB_NAME,
        user=ANALYTICS_DB_USER,
        password=ANALYTICS_DB_PASSWORD,
    )


def parse_rows(path, spec, instrument, round_no, occasion):
    """Read and validate the whole file. Returns (rows, errors, warnings).

    Collects every error rather than stopping at the first, so one pass tells the
    researcher everything that needs fixing in the spreadsheet.
    """
    rows, errors, warnings = [], [], []
    known = set(spec["items"])

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return [], ["file is empty"], []

        headers = [h.strip() for h in reader.fieldnames]
        if ID_COLUMN not in headers:
            return [], [f"missing required column '{ID_COLUMN}'"], []

        present = [h for h in headers if h in known]
        unknown = [h for h in headers if h not in known and h != ID_COLUMN]
        missing = [i for i in spec["items"] if i not in headers]

        # An unknown column is refused rather than ignored: it usually means a
        # renamed or mistyped field, and ignoring it would silently drop real
        # responses.
        for h in unknown:
            errors.append(f"unknown column '{h}' (not an item of instrument '{instrument}')")
        for i in missing:
            errors.append(f"missing item column '{i}'")
        if errors:
            return [], errors, []

        seen = set()
        for lineno, raw in enumerate(reader, start=2):
            code = (raw.get(ID_COLUMN) or "").strip()
            if not code:
                errors.append(f"line {lineno}: blank {ID_COLUMN}")
                continue
            if len(code) > 16:
                errors.append(f"line {lineno}: {ID_COLUMN} '{code}' exceeds 16 characters")
                continue
            if code in seen:
                errors.append(f"line {lineno}: duplicate {ID_COLUMN} '{code}' in this file")
                continue
            seen.add(code)

            blanks = 0
            for item in present:
                value = (raw.get(item) or "").strip()
                if value == "":
                    blanks += 1
                    continue
                try:
                    number = Decimal(value)
                except (InvalidOperation, ValueError):
                    errors.append(f"line {lineno}: {item} = '{value}' is not a number")
                    continue
                if not (spec["scale_min"] <= number <= spec["scale_max"]):
                    errors.append(
                        f"line {lineno}: {item} = {number} outside "
                        f"{spec['scale_min']}-{spec['scale_max']}"
                    )
                    continue
                rows.append((code, round_no, instrument, spec["version"], item,
                             number, spec["scale_min"], spec["scale_max"], occasion))

            if blanks > spec["max_blank"]:
                # Not an error: the response is real and is kept. The analysis
                # excludes it from the total per the pre-registered rule, and the
                # researcher is told now rather than discovering it at analysis.
                warnings.append(
                    f"{code}: {blanks} blank items (> {spec['max_blank']}); "
                    f"no total will be computed for this occasion"
                )

    return rows, errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="wide CSV to import")
    ap.add_argument("--instrument", default="cse", choices=sorted(INSTRUMENTS))
    ap.add_argument("--round", type=int, default=None,
                    help="round number 1-3; omit for instruments not tied to a round")
    ap.add_argument("--occasion", choices=["pre", "post"], default=None)
    ap.add_argument("--commit", action="store_true",
                    help="write to the database (default is validate only)")
    args = ap.parse_args()

    spec = INSTRUMENTS[args.instrument]

    if args.round is not None and not 1 <= args.round <= 3:
        print(f"error: --round must be 1-3, got {args.round}", file=sys.stderr)
        return 2

    required = spec.get("requires", ())
    if "round" in required and args.round is None:
        print(f"error: --round is required for instrument '{args.instrument}'",
              file=sys.stderr)
        return 2
    if "occasion" in required and args.occasion is None:
        print(f"error: --occasion is required for instrument '{args.instrument}'",
              file=sys.stderr)
        return 2
    if not os.path.exists(args.file):
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2

    rows, errors, warnings = parse_rows(
        args.file, spec, args.instrument, args.round, args.occasion
    )

    if errors:
        print(f"VALIDATION FAILED — {len(errors)} problem(s). Nothing was written.\n",
              file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    participants = len({r[0] for r in rows})
    print(f"instrument : {args.instrument} {spec['version']}")
    print(f"round      : {args.round if args.round is not None else '-'}"
          f"   occasion: {args.occasion or '-'}")
    print(f"validated  : {participants} participant(s), {len(rows)} response(s)")

    for w in warnings:
        print(f"  note: {w}")

    if not args.commit:
        print("\nValidate-only. Re-run with --commit to write.")
        return 0

    # Upsert so a corrected file replaces earlier values. Without this a re-run
    # would either fail on the unique constraint or, worse, double the row count
    # for anyone who resubmitted.
    sql = """
        INSERT INTO survey_response
            (participant_code, round_no, instrument, instrument_ver, item_code,
             response, scale_min, scale_max, occasion)
        VALUES %s
        ON CONFLICT (participant_code, round_no, instrument, item_code, occasion)
        DO UPDATE SET response = EXCLUDED.response,
                      instrument_ver = EXCLUDED.instrument_ver,
                      responded_at = now()
    """

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("\nerror: --commit needs psycopg2, which is not installed here.\n"
              "Run the import from the server, or: pip install psycopg2-binary",
              file=sys.stderr)
        return 2

    conn = None
    try:
        conn = connect()
        with conn, conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows, page_size=500)
        print(f"\nWrote {len(rows)} response(s) for {participants} participant(s).")
    except psycopg2.Error as exc:
        print(f"\ndatabase error, transaction rolled back: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
