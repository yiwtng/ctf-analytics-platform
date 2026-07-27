"""
make_practice_packets.py — Practice material for rater onboarding.

WHY THESE ARE WRITTEN RATHER THAN SAMPLED FROM PILOT DATA
The rubric's onboarding asks raters to score two practice reports, discuss, then
score a third. Sampled pilot reports would be whatever the generator happened to
produce that day — most likely three reports that are all fine, which teaches
nothing. These three are constructed so that each isolates a distinction the
rubric depends on and that raters reliably get wrong at first:

  1. Specific but not actionable, and technically true but misleading.
     The "100% accuracy" figure comes from zero submissions. A rater who reads
     accuracy as "are the numbers right" scores this 5; the rubric says an
     unhedged true-but-misleading statement belongs at 3.

  2. Actionable but not grounded.
     Good advice, none of it tied to anything this learner did. Tests whether
     the rater separates relevance from actionability.

  3. Contains a fabricated event.
     Everything reads well and one claim describes something that did not
     happen. Tests whether the rater actually checks claims against the evidence
     packet rather than judging fluency.

Each packet ships with the evidence the claims must be checked against, because
accuracy cannot be judged without it.

Practice ratings are excluded from analysis. The packets are marked PRACTICE on
every page so they cannot be confused with study material.

Usage:
    python tools/research/make_practice_packets.py --out practice/
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

CASES = [
    {
        "id": "PRACTICE-1",
        "evidence": [
            ("Challenges opened", "3 (web_recon_1, web_recon_2, proto_1)"),
            ("Flags submitted", "0"),
            ("Submission accuracy", "100% (0 correct of 0 submitted)"),
            ("Session time", "42 minutes"),
            ("Hints unlocked", "1"),
            ("SSH commands issued", "0"),
        ],
        "report": {
            "summary": "You achieved 100% submission accuracy this round and spent "
                       "42 minutes engaged with the material.",
            "strengths": [
                "Perfect submission accuracy — 100%.",
                "Opened 3 challenges across two categories.",
                "Sustained a 42-minute session.",
            ],
            "weaknesses": [
                "Persistence score of 40 is below the cohort median.",
            ],
            "recommendations": [
                "Keep up the strong accuracy.",
                "Consider working on persistence.",
            ],
        },
        "teaching": (
            "Accuracy is the dimension at issue. Every figure is correct: the "
            "learner did submit nothing and 0/0 is reported as 100%. But the "
            "report presents that as the learner's leading strength, which "
            "leaves a false impression of the round. The rubric puts unhedged "
            "true-but-misleading statements at 3, not 5. Specificity is high "
            "(4-5): the figures are precise. Actionability is low (1-2): "
            "\"consider working on persistence\" names no action."
        ),
    },
    {
        "id": "PRACTICE-2",
        "evidence": [
            ("Challenges opened", "5 (all web category)"),
            ("Flags submitted", "7 (2 correct, 5 incorrect)"),
            ("Submission accuracy", "29%"),
            ("Session time", "68 minutes"),
            ("Hints unlocked", "4"),
            ("SSH commands issued", "0"),
        ],
        "report": {
            "summary": "Web reconnaissance is a foundational skill and building it "
                       "systematically will serve you well.",
            "strengths": [
                "Willingness to engage with the material.",
                "Good use of available support resources.",
            ],
            "weaknesses": [
                "Room to grow in systematic enumeration.",
                "Could develop a more structured approach.",
            ],
            "recommendations": [
                "Practise directory enumeration with a wordlist before guessing paths.",
                "Read each server response fully before forming the next request.",
                "Keep a written note of what you have already ruled out.",
                "Work through the OWASP testing guide section on discovery.",
            ],
        },
        "teaching": (
            "Actionability is genuinely high (4-5): each recommendation names "
            "something the learner could start tomorrow. Relevance is the "
            "problem (1-2): nothing in the report refers to what this learner "
            "did. The 5 incorrect submissions, the 4 hints, the 29% accuracy — "
            "none of it appears. The same text could be sent to any "
            "participant unchanged. Specificity is likewise 1-2. This case "
            "exists because raters tend to reward good advice with a high "
            "relevance score."
        ),
    },
    {
        "id": "PRACTICE-3",
        "evidence": [
            ("Challenges opened", "6 (4 web, 2 protocol)"),
            ("Flags submitted", "9 (5 correct, 4 incorrect)"),
            ("Submission accuracy", "56%"),
            ("Session time", "74 minutes"),
            ("Hints unlocked", "2"),
            ("SSH commands issued", "0 — no SSH challenge was attempted"),
        ],
        "report": {
            "summary": "A solid round: 5 of 9 submissions correct across web and "
                       "protocol challenges, with steady progress after early "
                       "setbacks.",
            "strengths": [
                "5 correct flags from 9 attempts (56%), above the round median.",
                "Recovered after 3 consecutive incorrect submissions on web_recon_2 "
                "rather than abandoning it.",
                "Moved into the protocol category once the web set was exhausted.",
                "Used SSH pivoting effectively to reach the second host.",
            ],
            "weaknesses": [
                "Only 2 hints unlocked — earlier use might have saved time on "
                "web_recon_2.",
            ],
            "recommendations": [
                "On the next round, try the protocol challenges first while you "
                "are fresh.",
                "When three submissions fail in a row, re-read the challenge text "
                "before the fourth.",
            ],
        },
        "teaching": (
            "This report reads as the best of the three, and on relevance, "
            "specificity and actionability it is (4-5 throughout). But the "
            "fourth strength describes SSH pivoting that never happened: the "
            "evidence shows no SSH challenge was attempted. That is a "
            "fabricated event, which the rubric puts at accuracy = 1 regardless "
            "of how good the rest is. The point of this case is that fluency "
            "and accuracy are independent, and that accuracy requires checking "
            "claims against the packet rather than judging how the text reads."
        ),
    },
]

CSS = """
body{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;font-size:11pt;
     line-height:1.5;max-width:900px;margin:24px auto;padding:0 16px}
.banner{background:#000;color:#fff;padding:6px 12px;font-weight:700;letter-spacing:.06em;
        font-size:10pt;border-radius:3px}
h1{font-size:15pt;border-bottom:2px solid #000;padding-bottom:6px;margin-top:14px}
h2{font-size:12pt;margin:0 0 8px;background:#f0f0f0;padding:5px 8px;border-radius:3px}
h3{font-size:10pt;margin:12px 0 4px;color:#333}
.ev,.report{border:1px solid #999;padding:14px;border-radius:4px;margin-top:14px}
.ev table{width:100%;border-collapse:collapse;font-size:10pt}
.ev td{border-bottom:1px solid #ddd;padding:4px 6px}
.ev td:first-child{color:#555;width:44%}
.summary{font-style:italic}
ul{margin:4px 0 0 18px;padding:0}li{margin-bottom:3px}
.sheet{margin-top:20px;border:1.5px solid #000;padding:12px}
table.r{width:100%;border-collapse:collapse;margin-top:6px;font-size:10pt}
table.r th,table.r td{border:1px solid #666;padding:6px 8px;text-align:left}
table.r th{background:#eee}
.note{font-size:9.5pt;color:#444;margin-top:8px}
"""


def render_case(case, with_teaching):
    ev = "".join(f"<tr><td>{html.escape(k)}</td><td><strong>{html.escape(v)}</strong></td></tr>"
                 for k, v in case["evidence"])
    r = case["report"]

    def block(title, items):
        lis = "".join(f"<li>{html.escape(x)}</li>" for x in items)
        return f"<h3>{title}</h3><ul>{lis}</ul>"

    rows = "".join(f"<tr><td>{d}</td><td></td><td></td></tr>"
                   for d in ["Relevance", "Specificity", "Actionability", "Accuracy"])

    teaching = ""
    if with_teaching:
        teaching = (f'<div class="ev" style="border-color:#000">'
                    f'<h3 style="margin-top:0">Facilitator notes — not for the rater</h3>'
                    f'<p style="font-size:10pt">{html.escape(case["teaching"])}</p></div>')

    return f"""<div style="page-break-after:always">
<div class="banner">PRACTICE MATERIAL — NOT STUDY DATA — RATINGS EXCLUDED FROM ANALYSIS</div>
<h1>{case['id']}</h1>
<div class="ev"><h3 style="margin-top:0">Evidence for this learner</h3>
<table>{ev}</table>
<p class="note">Accuracy must be judged against this table. Check the figures;
do not assume a claim is right because it is precise.</p></div>
<div class="report"><h2>Report</h2>
<p class="summary">{html.escape(r['summary'])}</p>
{block("Strengths", r['strengths'])}
{block("Areas to improve", r['weaknesses'])}
{block("Recommendations", r['recommendations'])}</div>
<div class="sheet"><strong>Your ratings</strong> (1&ndash;5; comment required for 1 or 2)
<table class="r"><tr><th>Dimension</th><th>Rating</th><th>Comment</th></tr>{rows}</table>
<p class="note">Rate independently. Do not discuss until both of you have
finished PRACTICE-1 and PRACTICE-2.</p></div>
{teaching}
</div>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="practice/")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def write(name, cases, teaching):
        body = "".join(render_case(c, teaching) for c in cases)
        (out / name).write_text(
            f"<!doctype html><meta charset='utf-8'><title>{name}</title>"
            f"<style>{CSS}</style>{body}", encoding="utf-8")
        return name

    # Raters get 1 and 2, discuss, then 3. Splitting the files enforces the
    # sequence: handing over all three at once invites reading ahead, and the
    # discussion step is where the anchors actually get calibrated.
    files = [
        write("rater_practice_round1.html", CASES[:2], False),
        write("rater_practice_round2.html", CASES[2:], False),
        write("FACILITATOR_all_cases_with_notes.html", CASES, True),
    ]

    print(f"Wrote {len(files)} file(s) to {out}/")
    for f in files:
        print(f"  {f}")
    print("\nSequence:")
    print("  1. Both raters read docs/instruments/feedback_quality_rubric.md")
    print("  2. Both rate rater_practice_round1.html independently")
    print("  3. Compare; discuss only where you disagree")
    print("  4. Both rate rater_practice_round2.html independently")
    print("  5. If you still disagree by more than 1 point on any dimension,")
    print("     revise the rubric anchors and record that it was revised")
    print("\n  FACILITATOR_all_cases_with_notes.html is for whoever runs the")
    print("  session. Do not give it to the raters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
