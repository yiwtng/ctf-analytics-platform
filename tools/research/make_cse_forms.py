"""
make_cse_forms.py — Generate printable, pre-randomised CSE questionnaire forms.

WHY A GENERATOR RATHER THAN ONE PRINTED SHEET
The instrument specifies that items are presented in a random order per
participant, so that the grouping by dimension is not visible and does not cue a
pattern of answers. A single printed sheet cannot do that. This produces N forms,
each with its own item order, so the paper administration keeps the property the
instrument was designed around.

WHY EVERY ITEM CARRIES ITS CODE
Each row prints its item code (cse_web_1, ...) in small type beside the response
boxes. Data entry then transcribes by code, never by position. With shuffled
forms, position-based entry would silently mis-assign every response on every
form -- an error that produces a complete, plausible dataset with the item
labels wrong, which no downstream check would catch.

The order is derived from the form number by a fixed, seeded shuffle, so the same
form number always yields the same order: forms can be reprinted, and a lost form
reconstructed, without keeping extra state.

Usage:
    python tools/research/make_cse_forms.py --count 40 --occasion pre --out forms_pre.html
    # then open in a browser and print (A4, one form per page)
"""

import argparse
import html
import random
import sys

# Item text is the authority in docs/instruments/self_efficacy_scale.md; this
# mirrors it. If an item is reworded there, bump the version in both places --
# responses to different wordings must stay distinguishable.
VERSION = "v1"

ITEMS = [
    ("cse_web_1", "Find pages or endpoints on a web application that are not linked from its visible pages."),
    ("cse_web_2", "Work out what a web application is doing from the responses it returns to my requests."),
    ("cse_proto_1", "Connect to a service over a raw TCP connection and work out what input it expects."),
    ("cse_proto_2", "Recognise from a service's replies when my input has been rejected, and adjust it."),
    ("cse_ssh_1", "Explore an unfamiliar Linux host from a shell and find files that were not pointed out to me."),
    ("cse_ssh_2", "Follow a lead found in one file to locate related information elsewhere on the host."),
    ("cse_blue_1", "Read a log or capture and identify which entries indicate suspicious activity."),
    ("cse_blue_2", "Reach a defensible conclusion from incomplete evidence, and say what is missing."),
    ("cse_acc_1", "Decide whether I have enough evidence to commit to an answer, rather than guessing."),
    ("cse_acc_2", "Check my own answer before submitting it."),
    ("cse_pers_1", "Keep working on a problem after my first approach has failed."),
    ("cse_pers_2", "Change strategy when repeating the same approach is not working."),
    ("cse_time_1", "Judge when to move on from a problem instead of continuing to spend time on it."),
    ("cse_time_2", "Work through a problem without getting stuck on details that do not matter."),
]

SCALE = list(range(0, 101, 10))

STEM = """The statements below describe things you might be asked to do in a
cybersecurity exercise. For each one, rate <strong>how confident you are that you
could do it right now</strong>.<br><br>
Answer for your <strong>present</strong> ability, not what you hope to achieve.
There is no right answer, and your responses are not part of any grade, do not
affect your standing on the course, and are not seen by anyone who grades you."""

ANCHORS = ("0 = cannot do at all &nbsp;·&nbsp; 50 = moderately certain I can do "
           "&nbsp;·&nbsp; 100 = highly certain I can do")

CSS = """
@page { size: A4; margin: 14mm; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       font-size: 10.5pt; color: #000; margin: 0; }
.form { page-break-after: always; }
.form:last-child { page-break-after: auto; }
h1 { font-size: 13pt; margin: 0 0 2mm 0; }
.meta { font-size: 9pt; color: #333; border-bottom: 1.2pt solid #000;
        padding-bottom: 2mm; margin-bottom: 3mm;
        display: flex; justify-content: space-between; }
.stem { font-size: 9.5pt; line-height: 1.45; margin-bottom: 2.5mm; }
.anchors { font-size: 9pt; font-weight: 600; text-align: center;
           border: 0.8pt solid #000; padding: 1.5mm; margin-bottom: 3mm; }
table { width: 100%; border-collapse: collapse; }
td { border-bottom: 0.4pt solid #bbb; padding: 1.6mm 1mm; vertical-align: middle; }
.num { width: 6mm; font-size: 9pt; color: #444; }
.txt { font-size: 9.5pt; line-height: 1.3; }
.code { font-family: ui-monospace, "SF Mono", Menlo, monospace;
        font-size: 7pt; color: #888; }
.boxes { white-space: nowrap; text-align: right; width: 78mm; }
.b { display: inline-block; width: 4.6mm; height: 4.6mm; border: 0.6pt solid #333;
     margin-left: 0.6mm; text-align: center; font-size: 5.5pt; color: #999;
     line-height: 4.6mm; }
.foot { margin-top: 4mm; font-size: 8pt; color: #555;
        border-top: 0.4pt solid #999; padding-top: 1.5mm; }
"""


def build_form(form_no, occasion, round_no):
    """One form. Order is seeded by form number, so it is reproducible."""
    rng = random.Random(f"cse-{VERSION}-{occasion}-{form_no}")
    order = ITEMS[:]
    rng.shuffle(order)

    rows = []
    for i, (code, text) in enumerate(order, 1):
        boxes = "".join(f'<span class="b">{v}</span>' for v in SCALE)
        rows.append(
            f'<tr><td class="num">{i}.</td>'
            f'<td class="txt">{html.escape(text)}<br>'
            f'<span class="code">{code}</span></td>'
            f'<td class="boxes">{boxes}</td></tr>'
        )

    return f"""<div class="form">
<h1>Cybersecurity Task Confidence</h1>
<div class="meta">
  <span><strong>Participant code:</strong> ____________</span>
  <span>Form {form_no:03d} &nbsp;·&nbsp; {occasion.upper()} &nbsp;·&nbsp; Round {round_no} &nbsp;·&nbsp; {VERSION}</span>
</div>
<div class="stem">{STEM}</div>
<div class="anchors">{ANCHORS}</div>
<table>{''.join(rows)}</table>
<div class="foot">
Tick one box per row. If you are unsure, give your best estimate rather than
leaving it blank. You may stop at any time without giving a reason.
<br><em>Data entry: transcribe by the small item code, not by row position —
row order differs between forms.</em>
</div>
</div>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=40, help="how many forms to generate")
    ap.add_argument("--occasion", choices=["pre", "post"], required=True)
    ap.add_argument("--round", type=int, default=None,
                    help="round number shown on the form; defaults to 1 for pre, 3 for post")
    ap.add_argument("--out", default=None, help="output HTML file")
    args = ap.parse_args()

    if args.count < 1 or args.count > 500:
        print("error: --count must be 1-500", file=sys.stderr)
        return 2

    round_no = args.round if args.round is not None else (1 if args.occasion == "pre" else 3)
    out = args.out or f"cse_forms_{args.occasion}.html"

    forms = "\n".join(build_form(n, args.occasion, round_no)
                      for n in range(1, args.count + 1))

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"<!doctype html><meta charset='utf-8'>"
                 f"<title>CSE forms — {args.occasion}</title>"
                 f"<style>{CSS}</style>{forms}")

    print(f"Wrote {args.count} form(s) to {out}")
    print(f"  occasion={args.occasion}  round={round_no}  instrument=cse {VERSION}")
    print("  Open in a browser and print at A4, 100% scale, one form per page.")
    print("  Each form has its own item order; hand out any form to any participant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
