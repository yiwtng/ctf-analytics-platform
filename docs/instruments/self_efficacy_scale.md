# Cybersecurity task self-efficacy scale (CSE)

**Purpose.** Measure whether participants' confidence in performing the specific
tasks the platform trains changes over the study, and whether that change differs
by condition (H3).

**Instrument.** `cse` · **version** v1 · **Stored in.** `survey_response`
**Scale.** 0–100 confidence, in steps of 10 · **Administered.** before Round 1
(`occasion='pre'`) and after Round 3 (`occasion='post'`)

---

## ⚠️ Status of this instrument — read before using it

**This scale was constructed for this study. It is not a previously validated
instrument, and it must not be described as one.**

It follows Bandura's methodological guidance for constructing self-efficacy scales
— items are task-specific rather than general, phrased as present capability
("can do") rather than intention ("will do"), and rated for strength on a 0–100
scale — but that guidance concerns *how to construct* such a scale, not evidence
that this particular set of items works.

What this obliges the paper to do:

- Report the scale's internal consistency (Cronbach's α) from this study's own
  data, and treat the H3 result as uninterpretable if α is unacceptable.
- Describe the scale as newly constructed in the Methods section, and list it in
  Limitations as an instrument without prior validation.
- Not compare the absolute values against published self-efficacy figures from
  other studies. Only the within-study change and the between-condition difference
  are interpretable.

An alternative would be to license a published, validated cybersecurity
self-efficacy scale. That is the stronger option if one can be obtained and its
items match these tasks; it was not available here.

---

## Administration

**Stem, shown once at the top:**

> The statements below describe things you might be asked to do in a
> cybersecurity exercise. For each one, rate **how confident you are that you
> could do it right now**.
>
> Answer for your **present** ability, not what you hope to achieve. There is no
> right answer, and your responses are not part of any grade.
>
> 0 = cannot do at all · 50 = moderately certain I can do · 100 = highly certain I
> can do

**Response format.** 0 to 100 in steps of 10.

**Order.** Items are presented in a random order per participant, so that the
grouping by dimension is not visible and does not cue a pattern of answers.

**Timing.** Before Round 1 and after Round 3. Not between rounds: three
administrations of the same items invites practice effects on the questionnaire
itself, and the primary comparison only needs the two endpoints.

---

## Items

Two items per dimension, so that each subscale has more than a single indicator
while the whole scale stays short enough to be answered carefully. 14 items total.

### Web reconnaissance
| Code | Item |
| --- | --- |
| `cse_web_1` | Find pages or endpoints on a web application that are not linked from its visible pages. |
| `cse_web_2` | Work out what a web application is doing from the responses it returns to my requests. |

### Protocol analysis
| Code | Item |
| --- | --- |
| `cse_proto_1` | Connect to a service over a raw TCP connection and work out what input it expects. |
| `cse_proto_2` | Recognise from a service's replies when my input has been rejected, and adjust it. |

### SSH pivoting
| Code | Item |
| --- | --- |
| `cse_ssh_1` | Explore an unfamiliar Linux host from a shell and find files that were not pointed out to me. |
| `cse_ssh_2` | Follow a lead found in one file to locate related information elsewhere on the host. |

### Blue-team analysis
| Code | Item |
| --- | --- |
| `cse_blue_1` | Read a log or capture and identify which entries indicate suspicious activity. |
| `cse_blue_2` | Reach a defensible conclusion from incomplete evidence, and say what is missing. |

### Accuracy
| Code | Item |
| --- | --- |
| `cse_acc_1` | Decide whether I have enough evidence to commit to an answer, rather than guessing. |
| `cse_acc_2` | Check my own answer before submitting it. |

### Persistence
| Code | Item |
| --- | --- |
| `cse_pers_1` | Keep working on a problem after my first approach has failed. |
| `cse_pers_2` | Change strategy when repeating the same approach is not working. |

### Time efficiency
| Code | Item |
| --- | --- |
| `cse_time_1` | Judge when to move on from a problem instead of continuing to spend time on it. |
| `cse_time_2` | Work through a problem without getting stuck on details that do not matter. |

---

## Scoring

- **Total CSE score** = mean of all 14 items (0–100).
- **Subscale scores** = mean of the two items per dimension. Two-item subscales are
  reported descriptively only; internal consistency is not meaningful at k=2, and
  no inferential claim is made per subscale.
- Reverse-scored items: **none.** All items are positively worded. This is
  deliberate — reverse wording is a common source of confusion in a second language
  and would trade one bias for a worse one.
- **Missing items:** if a participant leaves more than two items blank, the total is
  not computed for that participant and the case is treated as missing on H3.

## Analysis

The primary H3 comparison is the **change** in total CSE score, pre to post,
between conditions (Mann–Whitney U, one-tailed, as pre-registered). Cronbach's α is
reported for the 14-item total at both occasions.

---

## ⚠️ What this instrument cannot show

Self-efficacy is self-reported confidence, not competence. The two can move in
opposite directions: a learner who receives detailed diagnostic feedback may
become *less* confident precisely because they now see what they did not know —
which would be a meaningful and interpretable finding, not a failure of the
intervention. It should not be read as a proxy for skill; skill is measured
separately and behaviourally.

The treatment group also visibly receives more material than the control group, so
a difference in self-reported confidence may partly reflect the attention received
rather than the feedback content. This is the same limitation recorded for the
primary outcome, and it applies with more force to a self-report measure.

---

## Recording

| Field | Value |
| --- | --- |
| `participant_code` | pseudonymous code |
| `round_no` | 1 for the pre administration, 3 for the post |
| `instrument` | `cse` |
| `instrument_ver` | `v1` |
| `item_code` | e.g. `cse_web_1` |
| `response` | 0–100 |
| `scale_min` / `scale_max` | 0 / 100 |
| `occasion` | `pre` or `post` |

---

## Satisfaction items (separate, existing)

The four single-item satisfaction ratings already collected — usability, challenge
quality, feedback quality, confidence improvement, each 1–5 — remain in
`participant_feedback` and are reported descriptively. They are **not** part of the
CSE scale and are not combined with it: single items measuring different constructs
should not be averaged into a scale, and "confidence improvement" as a one-item
retrospective judgement is a different measurement from a pre-post change in
task-specific confidence.
