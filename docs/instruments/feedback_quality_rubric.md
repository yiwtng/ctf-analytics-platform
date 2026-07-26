# Feedback quality rating rubric

**Purpose.** Evaluate the generated feedback itself (RQ4), and compare
model-generated feedback against the deterministic rule-based generator.

**Instrument version.** v1 · **Stored in.** `feedback_rating` (one row per rater ×
participant × round × generator source) · **Scale.** 1–5 on four dimensions

---

## ⚠️ Two rules that the comparison depends on

**1. Raters must not know which generator produced a report.** The comparison is
between model-generated and rule-based feedback; a rater who can tell them apart is
rating their expectation of a language model, not the text. Reports are presented
without any label, header, or formatting difference that identifies the source.

**2. Presentation order must be randomised per participant.** Both reports for the
same participant-round are rated, and if the model-generated one always came first,
order effects and the rater's fatigue would be confounded with source.

Raters do see the **underlying evidence** for the participant (the same packet used
for the skill rubric, minus the automated scores), because the *accuracy* dimension
cannot be judged without it — a claim can only be checked against what actually
happened.

---

## The four dimensions

They are rated separately because they fail separately. Feedback can be specific
without being actionable ("you issued 16 failed authentications" — true, precise,
and no help), or actionable without being grounded ("practise port forwarding" —
useful advice, but not tied to anything this learner did). Collapsing them would
hide exactly the distinction the study is testing.

### Relevance — is this about *this* learner?

| | |
| --- | --- |
| **5** | Every substantive statement pertains to what this learner actually did. Reads as written for them. |
| **4** | Mostly specific to the learner; one or two generic passages. |
| **3** | A mix; roughly half could apply to any learner. |
| **2** | Mostly generic advice with a few personalised touches. |
| **1** | Could be sent to any participant unchanged. |

### Specificity — does it cite concrete evidence?

| | |
| --- | --- |
| **5** | Claims are tied to named quantities or events ("6 SSH commands", "no submissions recorded"). |
| **4** | Mostly concrete; some claims left at the level of "limited activity". |
| **3** | Some concrete references, much vague characterisation. |
| **2** | Largely vague; evidence gestured at but not stated. |
| **1** | No concrete evidence referenced anywhere. |

*Specificity is about precision of reference, not about being correct — a precisely
stated wrong number scores high here and low on accuracy.*

### Actionability — can the learner do something tomorrow?

| | |
| --- | --- |
| **5** | Recommendations name a concrete next step the learner could begin immediately. |
| **4** | Mostly concrete steps; one or two are directional only. |
| **3** | Mixed: some steps, some exhortation ("practise more"). |
| **2** | Mostly exhortation, little that specifies an action. |
| **1** | No actionable guidance. |

*Judge whether the step is concrete, not whether you agree it is the best step.*

### Accuracy — is every claim supported by the evidence?

| | |
| --- | --- |
| **5** | Every factual claim checks out against the evidence packet. Where the data are thin or misleading, the report says so. |
| **4** | All claims supported; a minor imprecision that does not mislead. |
| **3** | One claim not supported by the evidence, or a figure misstated in a way that could mislead. |
| **2** | Several unsupported claims, or one substantially wrong claim about performance. |
| **1** | Contains a fabricated event or a materially false statement about the learner. |

**Check the numbers.** If a report says six commands, count them in the packet.
This dimension is the one that requires work; the others are judgements.

**Credit appropriate hedging.** A report that notes an accuracy of 100% arises from
zero submissions, rather than presenting it as a strength, is *more* accurate than
one that reports the figure without qualification. Unhedged technically-true
statements that leave a false impression belong at 3, not 5.

---

## Rater onboarding

1. Read this rubric.
2. Rate **two practice reports** from pilot data independently.
3. Discuss disagreements with the other rater(s) — the only permitted discussion.
4. Rate a third practice report. If agreement remains poor, revise the anchors
   before real rating begins, and record that the rubric was revised.

Practice reports are excluded from analysis.

---

## Recording

| Field | Value |
| --- | --- |
| `rater_id` | anonymous rater code, e.g. `E01` |
| `participant_code` | pseudonymous code |
| `round_no` | 1, 2 or 3 |
| `feedback_source` | **filled in by the study coordinator after rating**, never by the rater |
| `relevance`, `specificity`, `actionability`, `accuracy` | 1–5 |
| `comment` | free text; required whenever any dimension is rated 1 or 2 |

`feedback_source` is completed from the coordinator's blinding key once ratings are
submitted. A rater who fills it in has, by definition, not been blind.

At least **two independent raters per report** are required for Cohen's κ.

---

## Note on what this instrument can and cannot show

It measures the quality of the text as judged by domain experts. It does not
measure whether the feedback changed the learner's behaviour — that is RQ1, and it
is answered by the skill trajectory, not here. A report can be rated excellent and
still not help, and the study is designed so that those two questions are answered
by separate evidence.
