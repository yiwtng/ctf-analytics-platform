# Expert skill rating rubric

**Purpose.** Provide the human criterion against which the automated
seven-dimension measure is validated (RQ2). Agreement between raters is reported
as ICC; agreement between the expert mean and the automated score is the
criterion-validity evidence.

**Instrument version.** v1 · **Stored in.** `expert_rating` (one row per rater ×
participant × round × dimension) · **Scale.** 0–100

---

## ⚠️ Rule that decides whether this instrument is usable at all

**Raters must never see the automated score for the participant they are rating.**

If they do, the ICC no longer measures agreement between an automated judgment and
an independent human judgment — it measures how well a human can copy a number
they were shown. The correlation would be high and would mean nothing. Every
validity claim in RQ2 rests on this separation.

Concretely, the rating packet must contain the raw evidence and nothing else:

| Include | Exclude |
| --- | --- |
| Event timeline for that participant-round | Any dimension score |
| Challenges opened, and which were solved | The overall level (Developing / Intermediate / Advanced) |
| Submission history with verdicts | The generated feedback report |
| Hint unlocks | Any other participant's data |
| Commands issued, requests made, protocol exchanges | The participant's identity |

Participants appear as pseudonymous codes. Raters work independently and do not
discuss cases with each other before all ratings are submitted.

---

## How to rate

For each of the seven dimensions, judge **how much competence the evidence
demonstrates**, on 0–100. Use the bands below as anchors; intermediate values are
expected and encouraged.

Three instructions that matter more than the bands:

1. **Rate the evidence, not the person.** Sparse evidence is not weak
   performance. If a participant barely engaged with the tasks a dimension draws
   on, that dimension has little to judge — record it as *insufficient evidence*
   (see below) rather than guessing low.
2. **Do not reward volume for its own sake.** Forty near-identical requests are
   weaker evidence of reconnaissance skill than six well-chosen ones. The
   question is whether the behaviour shows *adaptation* to what was learned.
3. **Do not penalise a different-but-valid approach.** Several routes solve most
   of these tasks.

### Insufficient evidence

If the evidence for a dimension is too thin to judge, **leave that dimension
unrated** rather than entering a low number. A guess entered as data is
indistinguishable from a judgment, and would corrupt both the ICC and the
criterion comparison. Record the reason in `notes`.

This will be common for the four task-specific dimensions, because a participant
who skipped a task family leaves nothing to rate there. That is expected and is
reported as such.

---

## Band anchors (apply to every dimension)

| Band | Interpretation |
| --- | --- |
| **81–100** | Behaviour a competent practitioner would recognise as their own: efficient, adapts to feedback from the system, few wasted actions, reaches the objective by a defensible route. |
| **61–80** | Clearly capable. Some inefficiency or a wrong turn, but recovers, and the overall approach is sound. |
| **41–60** | Partly capable. Recognisable strategy but applied inconsistently; progress owes something to repetition rather than reasoning. |
| **21–40** | Emerging. Attempts the right kind of action but without a coherent plan; little evidence of learning from what the system returned. |
| **0–20** | Little or no evidence of the skill, despite having engaged with the relevant tasks. |

---

## Dimension-specific guidance

### 1. Web Reconnaissance
Evidence: requests issued, endpoints probed, response codes encountered.
**High:** probes are informed by earlier responses — a 404 changes the next guess;
the participant finds non-obvious endpoints.
**Low:** a fixed wordlist sprayed regardless of what came back.

### 2. Protocol Analysis
Evidence: connections, greetings, authentication attempts, malformed input,
disconnects.
**High:** establishes the protocol's expectations quickly, then works within them;
malformed input is used deliberately to probe, not accidentally.
**Low:** repeats the same rejected exchange; never completes a handshake.

### 3. SSH Pivoting
Evidence: connections, commands issued, sequence of paths and files touched.
**High:** commands build on each other — enumeration leads to a specific target;
uses the filesystem as a source of information.
**Low:** a handful of context-free commands; no evidence of following a lead.

> Note for raters: SSH telemetry is self-reported by the challenge host, which
> participants can reach. Treat a suspiciously clean or suspiciously empty command
> history with the same scepticism you would apply to any self-reported log, and
> say so in `notes`.

### 4. Blue-team Analysis
Evidence: challenges opened, time before first submission, hint unlocks, verdicts.
**High:** reaches correct conclusions without hints; time profile suggests reading
and reasoning rather than guessing.
**Low:** unlocks hints immediately; submits rapidly and repeatedly.

### 5. Accuracy
Evidence: correct-to-incorrect submission ratio, and *what* the wrong answers were.
**High:** submits when the evidence supports it; wrong answers, where present, are
plausible near-misses.
**Low:** rapid-fire guessing.
**Watch:** a perfect ratio achieved by submitting once, or never, is not accuracy —
it is absence of evidence. Mark insufficient.

### 6. Persistence
Evidence: restarts, give-ups, errors and what followed them.
**High:** meets an obstacle and changes approach.
**Low:** abandons on first failure, or repeats the identical failing action.
**Distinguish** persistence from repetition: continuing unchanged is not
persistence.

### 7. Time Efficiency
Evidence: elapsed time from opening a challenge to submitting.
**High:** time spent is proportionate to difficulty.
**Low:** either near-instant submission (guessing) or long stretches with no
recorded activity.
**Careful:** absence of events is not evidence of thinking. A long gap may mean the
participant left. Prefer *insufficient evidence* over inferring either.

---

## Rater onboarding (do this before any real ratings)

1. Read this rubric.
2. Rate **two practice cases** taken from pilot data, independently.
3. Compare with the other rater(s) and discuss where the bands were read
   differently. This is the only point at which discussion is permitted.
4. Re-rate a third practice case. If agreement is still poor, revise the anchors
   *before* real rating begins — and record that the rubric was revised.

Practice cases are excluded from all analysis.

---

## Recording

| Field | Value |
| --- | --- |
| `rater_id` | anonymous rater code, e.g. `E01` |
| `participant_code` | pseudonymous code from the packet |
| `round_no` | 1, 2 or 3 |
| `dimension` | one of the seven engine dimension names |
| `score` | 0–100, or omit the row entirely if insufficient evidence |
| `notes` | reason for an omission, or anything that qualifies the score |

At least **two independent raters per participant-round** are required; ICC cannot
be computed otherwise.
